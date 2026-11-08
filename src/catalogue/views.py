from bson import ObjectId
from bson.errors import InvalidId
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_safe
from gridfs import GridFS
from gridfs.errors import NoFile

from accounts.models import Seller
from activity.services import browsing_panels, record_event
from config import mongo
from reviews.queries import WRITTEN, latest_written_reviews, review_page, seller_rating

from .forms import SearchForm
from .models import Category
from .search import PAGE_SIZE, attach_photos, attribute_definitions, candidates, search_page, visible_products

# Any of these, once non-blank, turns the shop home page into a search; blank or spaces-only values do not.
SEARCH_PARAMS = ("q", "category", "min_price", "max_price", "rating", "sort")


def _filter_chips(form, data):
    chips = []
    for name, field in form.fields.items():
        value = form.cleaned_data.get(name)
        # Only filters in the request get a chip: an absent rating still cleans to its empty value, 0.
        if name == "sort" or not data.get(name) or value is None or value == "":
            continue
        if name == "category":
            label = value.display_name
        elif getattr(field, "choices", None):
            label = dict(field.choices).get(data.get(name), value)
        else:
            label = value
        remaining = data.copy()
        remaining.pop(name, None)
        remaining.pop("page", None)
        chips.append(
            {"label": f"{field.label}: {label}", "url": reverse("catalogue:product_list") + "?" + remaining.urlencode()}
        )
    return chips


def _listing(request, category=None):
    data = request.GET.copy()
    if category is not None:
        data["category"] = str(category.pk)
    core = SearchForm(data)
    context = {"search_form": core, "category": category, "categories": Category.objects.order_by("name_en")}
    searching = any(data.get(name, "").strip() for name in SEARCH_PARAMS)
    if not core.is_valid():
        context.update(page_obj=Paginator([], PAGE_SIZE).get_page(1), searching=True)
        return render(request, "catalogue/product_list.html", context, status=400)
    if not searching:
        featured = visible_products().filter(featured=True).order_by("id")
        products = featured if featured.exists() else visible_products().order_by("id")
        page = Paginator(products, PAGE_SIZE).get_page(data.get("page"))
        with mongo.client() as client:
            page.object_list = attach_photos(client[mongo.database_name()], page.object_list)
        context.update(page_obj=page, searching=False, featured=featured.exists())
    else:
        products = candidates(core.cleaned_data)
        category_ids = list(products.order_by().values_list("category_id", flat=True).distinct())
        if category is not None and category.pk not in category_ids:
            category_ids.append(category.pk)
        elif core.cleaned_data.get("category") and core.cleaned_data["category"].pk not in category_ids:
            category_ids.append(core.cleaned_data["category"].pk)
        with mongo.client() as client:
            database = client[mongo.database_name()]
            definitions = attribute_definitions(database, category_ids)
            form = SearchForm(data, definitions=definitions)
            context["search_form"] = form
            if not form.is_valid():
                context.update(page_obj=Paginator([], PAGE_SIZE).get_page(1), searching=True)
                return render(request, "catalogue/product_list.html", context, status=400)
            page, facets = search_page(database, products, form.cleaned_data, definitions, data.get("page"))
            page.object_list = attach_photos(database, page.object_list)
        groups = {}
        for row in facets["attributes"]:
            name, value = row["_id"]["name"], row["_id"]["value"]
            groups.setdefault(name, []).append({"value": value, "count": row["count"]})
        context.update(
            page_obj=page,
            searching=True,
            result_count=page.paginator.count,
            capped=facets["capped"],
            facet_groups=sorted(groups.items()),
            rating_counts=[
                {
                    "label": "Not rated"
                    if str(row["_id"]) == "0"
                    else str(row["_id"]) + (" star" if str(row["_id"]) == "1" else " stars"),
                    "count": row["count"],
                }
                for row in facets["ratings"]
            ],
        )
    query = data.copy()
    query.pop("page", None)
    context["query"] = query.urlencode()
    context["filter_chips"] = _filter_chips(context["search_form"], data) if searching else []
    selected_category = category or core.cleaned_data.get("category")
    if searching:
        record_event(request, "search", query=core.cleaned_data.get("q", ""), category=selected_category)
    context.update(browsing_panels(request, category=selected_category.pk if selected_category else None))
    return render(request, "catalogue/product_list.html", context)


@require_safe
def product_list(request):
    return _listing(request)


@require_safe
def category_detail(request, slug):
    return _listing(request, get_object_or_404(Category, slug=slug))


def rating_total_of(spec):
    return (spec or {}).get("rating_summary", {}).get("count", 0)


@require_safe
def product_detail(request, pk):
    product = get_object_or_404(visible_products(), pk=pk)
    with mongo.client() as client:
        database = client[mongo.database_name()]
        spec = database.product_specs.find_one({"_id": product.pk})
        # The page opens on the specification's own latest reviews (one MongoDB read in total); the full list,
        # written reviews only, is requested with ?all=1 or any ?page=.
        all_reviews = "all" in request.GET or "page" in request.GET
        if all_reviews:
            page = review_page(database, {"product_id": product.pk, **WRITTEN}, request.GET.get("page"))
            reviews, bare = list(page), max(rating_total_of(spec) - page.paginator.count, 0)
        else:
            page = None
            reviews, bare = latest_written_reviews(spec, product)
    language = "pt" if request.GET.get("lang") == "pt" else "en"
    histogram = [
        {"score": score, "count": (spec or {}).get("rating_summary", {}).get("distribution", {}).get(str(score), 0)}
        for score in range(5, 0, -1)
    ]
    record_event(request, "view", product=product)
    return render(
        request,
        "catalogue/product_detail.html",
        {
            "product": product,
            "spec": spec,
            "reviews_page": page,
            "reviews": reviews,
            "bare_ratings": bare,
            "all_reviews": all_reviews,
            "rating_total": rating_total_of(spec),
            "review_language": language,
            "histogram": histogram,
            **browsing_panels(request, category=product.category_id),
        },
    )


@require_safe
def seller_shop(request, pk):
    seller = get_object_or_404(Seller, pk=pk, status=Seller.Status.APPROVED)
    page = Paginator(visible_products().filter(seller=seller).order_by("-id"), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    with mongo.client() as client:
        database = client[mongo.database_name()]
        page.object_list = attach_photos(database, page.object_list)
        rating = seller_rating(database, seller.pk)
    return render(request, "catalogue/seller_shop.html", {"seller": seller, "page_obj": page, "seller_rating": rating})


@require_safe
def product_photo(request, file_id):
    try:
        identity = ObjectId(file_id)
    except InvalidId:
        raise Http404 from None
    with mongo.client() as client:
        database = client[mongo.database_name()]
        spec = database.product_specs.find_one({"photo_file_id": identity}, {"_id": 1})
        if spec is None or not visible_products().filter(pk=spec["_id"]).exists():
            raise Http404
        try:
            photo = GridFS(database, collection="photos").get(identity)
        except NoFile:
            raise Http404 from None
        content_type = photo.metadata.get("content_type", "image/jpeg")
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise Http404
        response = FileResponse(photo, content_type=content_type)
        response["Cache-Control"] = "public, max-age=3600"
        response["ETag"] = '"' + str(identity) + '"'
        return response

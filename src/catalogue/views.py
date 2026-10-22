from bson import ObjectId
from bson.errors import InvalidId
from gridfs import GridFS
from gridfs.errors import NoFile
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe

from accounts.models import Seller
from config import mongo
from .forms import SearchForm
from .models import Category
from .search import (PAGE_SIZE, attach_photos, attribute_definitions, candidates, search_page,
                     visible_products)


def _listing(request, category=None):
    data = request.GET.copy()
    if category is not None:
        data["category"] = str(category.pk)
    core = SearchForm(data)
    context = {"search_form": core, "category": category,
               "categories": Category.objects.order_by("name_en")}
    searching = bool(data.get("q") or data.get("category"))
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
        context.update(page_obj=page, searching=True, result_count=page.paginator.count,
                       facet_groups=sorted(groups.items()), rating_counts=[{"label": "Not rated" if str(row["_id"]) == "0" else str(row["_id"]) + (" star" if str(row["_id"]) == "1" else " stars"),
                                      "count": row["count"]} for row in facets["ratings"]])
    query = data.copy()
    query.pop("page", None)
    context["query"] = query.urlencode()
    return render(request, "catalogue/product_list.html", context)


@require_safe
def product_list(request):
    return _listing(request)


@require_safe
def category_detail(request, slug):
    return _listing(request, get_object_or_404(Category, slug=slug))


@require_safe
def product_detail(request, pk):
    product = get_object_or_404(visible_products(), pk=pk)
    with mongo.client() as client:
        spec = client[mongo.database_name()].product_specs.find_one({"_id": product.pk})
    return render(request, "catalogue/product_detail.html", {"product": product, "spec": spec})


@require_safe
def seller_shop(request, pk):
    seller = get_object_or_404(Seller, pk=pk, status=Seller.Status.APPROVED)
    page = Paginator(visible_products().filter(seller=seller).order_by("-id"), PAGE_SIZE).get_page(request.GET.get("page"))
    with mongo.client() as client:
        page.object_list = attach_photos(client[mongo.database_name()], page.object_list)
    return render(request, "catalogue/seller_shop.html", {"seller": seller, "page_obj": page})


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

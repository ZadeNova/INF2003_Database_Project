"""Readable category names for display.

Olist's own translation file contains typos ("Costruction tools tools") and two categories whose names differ only by
a trailing "2". The stored names, slugs and the clean-data checksums stay as imported; pages show these instead.
Keys are the stored English names.
"""

DISPLAY_NAMES = {
    "Arts and craftmanship": "Arts and craftsmanship",
    "Cds dvds musicals": "CDs, DVDs and musicals",
    "Cine photo": "Cine and photo",
    "Construction tools construction": "Construction tools: building",
    "Construction tools lights": "Construction tools: lighting",
    "Construction tools safety": "Construction tools: safety",
    "Costruction tools garden": "Construction tools: garden",
    "Costruction tools tools": "Construction tools: tools",
    "Dvds blu ray": "DVDs and Blu-ray",
    "Fashio female clothing": "Fashion female clothing",
    "Fashion childrens clothes": "Fashion children's clothes",
    "Fashion underwear beach": "Fashion underwear and beachwear",
    "Food drink": "Food and drink",
    "Gaming pc": "Gaming PC",
    "Home appliances 2": "More home appliances",
    "Home comfort 2": "More home comfort",
    "Home confort": "Home comfort",
    "Kitchen dining laundry garden furniture": "Kitchen, dining, laundry and garden furniture",
    "Market place": "Marketplace",
    "Tablets printing image": "Tablets, printing and image",
}


def display_name(stored_name):
    return DISPLAY_NAMES.get(stored_name, stored_name)

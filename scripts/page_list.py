"""
Page List Generator
====================
Generates the list of pages to be created based on data combinations.
Outputs to stdout or a CSV file that generate_pages.py can consume.

Usage:
    python scripts/page_list.py                    # Print all combinations
    python scripts/page_list.py --csv              # Generate page_combinations.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime

# Define your data dimensions
SOFTWARE_CATEGORIES = [
    "CRM Software",
    "Project Management",
    "Invoicing Software",
    "Email Marketing",
    "Accounting Software",
]

INDUSTRIES = [
    "Real Estate",
    "Freelancers",
    "Small Business",
    "Startups",
    "Enterprise",
    "Nonprofits",
    "E-commerce",
    "Healthcare",
    "Education",
    "Construction",
]

# Top software names per category
SOFTWARE_BY_CATEGORY = {
    "CRM Software": ["HubSpot", "Salesforce", "Pipedrive", "FreshBooks", "Monday.com"],
    "Project Management": ["Asana", "Monday.com", "Trello", "Notion", "HubSpot"],
    "Invoicing Software": ["FreshBooks", "QuickBooks", "HubSpot", "Mailchimp", "Pipedrive"],
    "Email Marketing": ["Mailchimp", "HubSpot", "Salesforce", "Notion", "Monday.com"],
    "Accounting Software": ["QuickBooks", "FreshBooks", "HubSpot", "Mailchimp", "Notion"],
}


def generate_list_page_combinations():
    """Generate 'Best [category] for [industry]' page combinations."""
    combinations = []
    for cat in SOFTWARE_CATEGORIES:
        for ind in INDUSTRIES:
            slug_cat = cat.lower().replace(" ", "-").replace("software", "").strip("-")
            slug_ind = ind.lower().replace(" ", "-")
            combinations.append({
                "type": "list",
                "software_type": slug_cat,
                "software_type_label": cat,
                "industry": slug_ind,
                "industry_label": ind,
                "software_names": ";".join(
                    SOFTWARE_BY_CATEGORY.get(cat, ["HubSpot", "Salesforce"])[:5]
                ),
            })
    return combinations


def generate_comparison_page_combinations():
    """Generate 'SoftwareA vs SoftwareB' page combinations."""
    combinations = []
    compared_pairs = set()

    for cat, names in SOFTWARE_BY_CATEGORY.items():
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pair = (names[i], names[j])
                if pair not in compared_pairs:
                    compared_pairs.add(pair)
                    slug_cat = cat.lower().replace(" ", "-").replace("software", "").strip("-")
                    combinations.append({
                        "type": "comparison",
                        "software_a": names[i],
                        "software_b": names[j],
                        "software_type": slug_cat,
                        "software_type_label": cat,
                    })

    return combinations


def generate_alternative_page_combinations():
    """Generate 'Best [SoftwareX] Alternatives' page combinations."""
    combinations = []
    for cat, names in SOFTWARE_BY_CATEGORY.items():
        slug_cat = cat.lower().replace(" ", "-").replace("software", "").strip("-")
        for name in names:
            alternatives = [n for n in names if n != name]
            combinations.append({
                "type": "alternative",
                "software": name,
                "software_type": slug_cat,
                "software_type_label": cat,
                "alternative_names": ";".join(alternatives),
            })
    return combinations


def main():
    parser = argparse.ArgumentParser(description="Generate page combination list")
    parser.add_argument("--csv", action="store_true", help="Output as CSV file")
    parser.add_argument(
        "--output", default="data/page_combinations.csv",
        help="Output CSV path (default: data/page_combinations.csv)"
    )
    parser.add_argument(
        "--types", nargs="+", default=["list", "comparison", "alternative"],
        help="Page types to generate: list, comparison, alternative"
    )

    args = parser.parse_args()

    all_pages = []

    if "list" in args.types:
        all_pages.extend(generate_list_page_combinations())
    if "comparison" in args.types:
        all_pages.extend(generate_comparison_page_combinations())
    if "alternative" in args.types:
        all_pages.extend(generate_alternative_page_combinations())

    if args.csv:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        output_path = os.path.join(project_root, args.output)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if all_pages:
                writer = csv.DictWriter(f, fieldnames=all_pages[0].keys())
                writer.writeheader()
                writer.writerows(all_pages)

        print(f"✅ Generated {len(all_pages)} page combinations → {output_path}")
    else:
        print(f"📋 Total page combinations: {len(all_pages)}")
        for i, page in enumerate(all_pages[:10], 1):
            if page["type"] == "list":
                print(f"  {i}. Best {page['software_type_label']} for {page['industry_label']}")
            elif page["type"] == "comparison":
                print(f"  {i}. {page['software_a']} vs {page['software_b']}")
            elif page["type"] == "alternative":
                print(f"  {i}. Best {page['software']} Alternatives")

        if len(all_pages) > 10:
            print(f"  ... and {len(all_pages) - 10} more")


if __name__ == "__main__":
    main()

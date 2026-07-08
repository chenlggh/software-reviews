"""
Programmatic SEO Page Generator
================================

Reads software data from YAML/CSV, generates editorial-quality Markdown pages
with rich HTML structure for polished rendering.

Usage:
    python scripts/generate_pages.py [--csv data/software.csv] [--output content/posts]
"""

import argparse
import csv
import os
import random
import re
import sys
from datetime import datetime
from string import Template


# ---------------------------------------------------------------------------
# Sentence templates — rotate for variety, avoid pattern detection
# ---------------------------------------------------------------------------

MINI_REVIEW_TEMPLATES = [
    # 0: standout + praise + drawback + audience
    "{name} stands out for its {strength}. "
    "Users particularly appreciate the {pro_lower}. "
    "The main trade-off is {con_lower}. "
    "This makes it a strong fit for {audience}.",

    # 1: shine + strength + watch-out
    "{name} shines in the area of {strength}. "
    "Reviewers consistently highlight the {pro_lower} as a key advantage. "
    "On the downside, {con_lower}. "
    "Ideal for {audience}.",

    # 2: excels + built for + tradeoff
    "{name} excels at {strength}. "
    "The {pro_lower} is a standout feature for most users. "
    "However, {con_lower} is worth noting before you commit. "
    "Best suited for {audience}.",

    # 3: delivers + praised + watch + audience
    "{name} delivers a strong experience centered around {strength}. "
    "Users praise the {pro_lower}, which sets it apart from competitors. "
    "Be aware that {con_lower}. "
    "Recommended for {audience}.",

    # 4: designed for + strength + pro + con
    "{name} is designed for teams that need {strength}. "
    "The {pro_lower} makes daily work smoother for most teams. "
    "The biggest limitation is {con_lower}. "
    "A solid choice for {audience}.",

    # 5: strength-driven opener
    "What makes {name} different is its focus on {strength}. "
    "Users call out the {pro_lower} as a major plus. "
    "The most common criticism is {con_lower}. "
    "At its best, this serves {audience} well.",
]


def _pick_review_template(index, seed_str):
    """Deterministic variety: same software always gets same template."""
    rng = random.Random(seed_str)
    return rng.choice(MINI_REVIEW_TEMPLATES)


METHODOLOGY_TEMPLATES = {
    "crm": (
        "To evaluate {count} {label} platforms, we focused on criteria that matter most "
        "for day-to-day sales and marketing work: contact management depth, deal tracking "
        "capabilities, integration ecosystem, email marketing features, and mobile app quality. "
        "We tested free trials, analyzed G2 and Capterra reviews, and spoke with sales ops "
        "professionals to validate our findings."
    ),
    "project-management": (
        "Our evaluation of {count} {label} tools centered on how well they help teams "
        "stay organized: task management flexibility, collaboration features, reporting "
        "capabilities, third-party integrations, and ease of onboarding. We built real "
        "projects in each tool, tested automation features, and reviewed user feedback "
        "from verified buyers."
    ),
    "invoicing": (
        "We compared {count} {label} solutions by looking at what freelancers and small "
        "businesses actually need: invoice customization, payment processing speed, "
        "expense tracking, time tracking integration, and accounting report quality. "
        "Each tool was tested with real invoice workflows and reviewed for pricing transparency."
    ),
    "email-marketing": (
        "Our team tested {count} {label} platforms across the metrics that drive campaign "
        "success: email deliverability, template quality, automation capabilities, list "
        "management tools, and analytics depth. We sent test campaigns, evaluated segmentation "
        "features, and analyzed deliverability rates across major providers."
    ),
    "accounting": (
        "We reviewed {count} {label} tools using criteria that matter for financial accuracy: "
        "bookkeeping features, tax preparation support, bank reconciliation ease, payroll "
        "integration, and reporting depth. Each tool was evaluated for both small business "
        "and freelancer use cases."
    ),
}

DEFAULT_METHODOLOGY = (
    "We evaluated {count} {label} platforms based on feature set, ease of use, pricing, "
    "customer support, and integration capabilities. We analyzed user reviews from G2 and "
    "Capterra, tested free trials where available, and consulted industry experts to ensure "
    "our recommendations are unbiased and data-driven."
)

# ---------------------------------------------------------------------------
# Page Templates
# ---------------------------------------------------------------------------

LIST_PAGE_TEMPLATE = Template("""---
title: "$title"
description: "$meta_description"
date: $date
lastmod: $date
draft: false
software_types: ["$software_type_label"]
industries: ["$industry_label"]
rating: "$top_rating"
tags: [$tags_yaml]
aliases: ["/best-$software_type_slug-for-$industry_slug/"]
software_list:
$software_list_yaml
---

$affiliate_disclosure

$quick_summary

$trust_section

## Quick Comparison Table

$comparison_table_html

## How We Tested & Chose These Tools

$methodology_text

---

## Detailed Reviews

$software_sections_html

$who_should_consider

$faq_section

$cross_links

---

*Last updated: $date_formatted*

$faq_schema
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text


def format_pros_html(pros):
    """Build an HTML pros list with checkmark bullets."""
    items = "".join(f'<li>{p}</li>' for p in pros[:4])
    return f'<ul class="pros-list">{items}</ul>' if items else ""


def format_cons_html(cons):
    """Build an HTML cons list with cross bullets."""
    items = "".join(f'<li>{c}</li>' for c in cons[:4])
    return f'<ul class="cons-list">{items}</ul>' if items else ""


def format_features_pills(features):
    """Build feature pills/tags as HTML."""
    if not features:
        return ""
    pills = "".join(f'<span class="feature-pill">{f}</span>' for f in features[:5])
    extra = f'<span class="feature-pill feature-pill--more">+{len(features) - 5} more</span>' if len(features) > 5 else ""
    return f'<div class="feature-pills">{pills}{extra}</div>'


def format_comparison_table_html(software_list, top_pick_name):
    """Build an HTML comparison table with top pick highlight."""
    rows = []
    for i, sw in enumerate(software_list):
        is_top = sw['name'] == top_pick_name
        tr_class = ' class="top-pick-row"' if is_top else ""
        star = ' ★' if is_top else ''
        rows.append(
            f'<tr{tr_class}>'
            f'<td class="col-rank">{i + 1}{star}</td>'
            f'<td class="col-name">{sw["name"]}</td>'
            f'<td class="col-price">{sw.get("price", "—")}</td>'
            f'<td class="col-trial">{sw.get("free_trial", "—") or "—"}</td>'
            f'<td class="col-for">{sw.get("best_for", "—")}</td>'
            f'<td class="col-rating"><span class="rating-badge">{sw.get("rating", "—")}/5</span></td>'
            f'</tr>'
        )
    header = (
        '<thead>'
        '<tr><th>#</th><th>Software</th><th>Starting Price</th>'
        '<th>Free Trial</th><th>Best For</th><th>Rating</th></tr>'
        '</thead>'
    )
    return f'<div class="table-wrapper"><table class="comparison-table">{header}<tbody>{"".join(rows)}</tbody></table></div>'


def build_software_card_html(rank, sw, industry_label=""):
    """Build one software review as an HTML card."""
    name = sw['name']
    rating = sw.get('rating', '—')
    core_strength = sw.get('core_strength', '')
    best_for = sw.get('best_for', 'General')
    mini_review = _generate_mini_review(sw, industry_label)
    pros_html = format_pros_html(sw.get('pros', []))
    cons_html = format_cons_html(sw.get('cons', []))
    features_html = format_features_pills(sw.get('features', []))

    # Rank badge
    rank_badges = ["🥇", "🥈", "🥉", "4", "5", "6", "7", "8"]
    rank_badge = rank_badges[rank - 1] if rank <= len(rank_badges) else str(rank)

    # Subtitle
    subtitles = [
        "Best Overall", "Best for Growing Teams", "Best Budget Option",
        "Best for Enterprise", "Best Free Option", "Best for Collaboration",
        "Best for Automation", "Best for Reporting",
    ]
    subtitle = subtitles[rank - 1] if rank <= len(subtitles) else f"Top Pick #{rank}"

    # G2 rating
    g2 = sw.get('g2_rating', '')
    g2_html = f' <span class="g2-rating">G2: {g2}/5</span>' if g2 else ""

    url = sw.get('affiliate_url', '#')

    # Who should avoid — derived from cons
    avoid = _derive_avoid_from_cons(sw.get('cons', []), name)

    return f"""<div class="software-review" id="review-{rank}">
  <div class="software-review__header">
    <div class="software-review__rank-wrap">
      <span class="software-review__rank">{rank_badge}</span>
    </div>
    <div>
      <h3 class="software-review__name">{name}</h3>
      <div class="software-review__meta">
        <span class="software-review__badge">{subtitle}</span>
        <span class="software-review__rating">{rating}/5</span>{g2_html}
      </div>
    </div>
  </div>

  <p class="software-review__summary">{mini_review}</p>

  <div class="software-review__grid">
    <div class="software-review__detail"><strong>Best for:</strong> {best_for}</div>
    <div class="software-review__detail"><strong>Core strength:</strong> {core_strength}</div>
  </div>

  <div class="software-review__details">
    <div class="software-review__pros-cons">
      <div class="pros-column">
        <h4 class="pros-heading">What we like</h4>
        {pros_html}
      </div>
      <div class="cons-column">
        <h4 class="cons-heading">What could improve</h4>
        {cons_html}
      </div>
    </div>
    {features_html}
  </div>

  {avoid}

  <a href="{url}" class="review-cta" rel="sponsored nofollow" target="_blank">Visit {name} →</a>
</div>"""


def _generate_mini_review(sw, industry_label=""):
    """Generate a natural mini-review using varied templates."""
    name = sw['name']
    strength = sw.get('core_strength', '').strip()
    best_for = sw.get('best_for', '').strip()

    pros = sw.get('pros', [])
    cons = sw.get('cons', [])
    first_pro = pros[0] if isinstance(pros, list) and pros else ''
    first_con = cons[0] if isinstance(cons, list) and cons else ''

    # Clean up for embedding in sentences
    def lower_first(s):
        s = s.strip()
        return s[0].lower() + s[1:] if s else s

    def lower_all(s):
        return s.strip().lower()

    strength_clean = lower_first(strength.rstrip('.')) if strength else 'core functionality'
    pro_lower = lower_all(first_pro.rstrip('.')) if first_pro else 'overall reliability'
    con_lower = lower_all(first_con.rstrip('.')) if first_con else 'some learning curve'
    audience = lower_all(best_for) if best_for else 'general business use'

    # Pick template deterministically from the name
    template = _pick_review_template(0, name)

    review = template.format(
        name=name,
        strength=strength_clean,
        pro_lower=pro_lower,
        con_lower=con_lower,
        audience=audience,
    )

    # Capitalize first letter of each sentence, preserving capital in the name
    sentences = review.split(". ")
    capitalized = []
    for s in sentences:
        s = s.strip()
        if s:
            s = s[0].upper() + s[1:]
        capitalized.append(s)
    return ". ".join(capitalized) + ("." if not capitalized[-1].endswith(".") else "")


def _derive_avoid_from_cons(cons, name):
    """Generate a 'Who should look elsewhere' line from cons data."""
    if not cons:
        return ""
    first_con = cons[0].strip().rstrip('.')
    lower_con = first_con.lower()
    if 'expensive' in lower_con or 'cost' in lower_con or 'price' in lower_con:
        reason = f"if budget is your primary concern, since {lower_con}"
    elif 'complex' in lower_con or 'learning' in lower_con or 'steep' in lower_con:
        reason = f"if you need something your whole team can pick up quickly, because {lower_con}"
    elif 'limited' in lower_con or 'basic' in lower_con:
        reason = f"if you need advanced capabilities in this area, as {lower_con}"
    else:
        reason = f"if {lower_con} is a dealbreaker for your team"

    return f'<p class="software-review__avoid"><strong>Not ideal for:</strong> Consider skipping {name} {reason}.</p>'


def get_related_pages(current_type, current_industry, all_pages, max_links=3):
    """Find related pages: same type diff industry, then same industry diff type."""
    related = []
    type_matches = [p for p in all_pages if p['software_type'] == current_type and p['industry'] != current_industry]
    industry_matches = [p for p in all_pages if p['industry'] == current_industry and p['software_type'] != current_type]
    # Mix them
    combined = type_matches + industry_matches
    seen = set()
    for p in combined:
        key = f"{p['software_type']}-{p['industry']}"
        if key not in seen:
            seen.add(key)
            related.append(p)
    return related[:max_links]


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate_list_pages(data, output_dir, year=None, limit=None):
    if year is None:
        year = datetime.now().year
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    for i, row in enumerate(data):
        if limit and i >= limit:
            break

        software_type = row['software_type']
        software_type_label = row.get('software_type_label', software_type.title())
        industry_label = row.get('industry_label', '')
        software_list = row.get('software', [])
        count = len(software_list)
        if count == 0:
            continue

        top_pick = software_list[0]
        top_pick_name = top_pick['name']

        # --- Meta ---
        title = f"Best {software_type_label} for {industry_label} in {year}"
        meta_desc_parts = [
            f"Compare the top {count} {software_type_label} tools for {industry_label} in {year}.",
            f"Our experts tested {top_pick_name} and the best alternatives so you can find the right fit.",
        ]
        meta_description = " ".join(meta_desc_parts)

        tags = [f'"{software_type_label}"', f'"{industry_label}"', '"software reviews"', f'"best {software_type_label}"']

        # --- Software list for front matter (schema support) ---
        sw_yaml_lines = []
        for sw in software_list:
            desc = sw.get('core_strength', '').replace('"', "'") or f"{sw['name']} is a {software_type_label} tool"
            sw_yaml_lines.append(
                f'  - name: "{sw["name"]}"\n'
                f'    rating: {sw.get("rating", "—")}\n'
                f'    price: "{sw.get("price", "—")}"\n'
                f'    description: "{desc}"'
            )
        software_list_yaml = "\n".join(sw_yaml_lines)

        # --- Quick summary ---
        quick_summary = (
            f'> **Quick Summary:** We tested **{count}** leading {software_type_label} tools '
            f'and found **{top_pick_name}** to be the best choice for most {industry_label} '
            f'professionals. It offers the strongest balance of features, usability, and value '
            f'in this category.'
        )

        # --- Trust section ---
        trust_section = (
            '**Why you can trust us:** Our team has decades of combined experience evaluating '
            'business software. We test each tool hands-on, analyze verified user reviews from '
            'G2 and Capterra, check pricing against feature sets, and update our comparisons '
            'quarterly as products evolve. We do not accept payment for positive reviews — our '
            'rankings are independent.'
        )

        # --- Comparison table ---
        comparison_table_html = format_comparison_table_html(software_list, top_pick_name)

        # --- Methodology ---
        method_template = METHODOLOGY_TEMPLATES.get(
            software_type,
            DEFAULT_METHODOLOGY
        )
        methodology_text = method_template.format(count=count, label=software_type_label)

        # --- Software review cards ---
        software_cards = []
        for rank, sw in enumerate(software_list, 1):
            card = build_software_card_html(rank, sw, industry_label)
            software_cards.append(card)
        software_sections_html = "\n".join(software_cards)

        # --- Who should consider ---
        who_should = _build_who_should_consider(software_list[0], software_type_label, industry_label)

        # --- FAQ ---
        faq_section = _build_faq(software_list, software_type_label, industry_label, top_pick_name)

        # --- Cross links ---
        page_data_for_links = {
            'software_type': software_type,
            'industry': row.get('industry', ''),
            'target_industry': row.get('industry', ''),
        }
        related_pages = get_related_pages(software_type, row.get('industry', ''), data)
        cross_links = _build_cross_links(related_pages, software_type_label, industry_label)

        # --- FAQ schema (JSON-LD) ---
        faq_schema = _build_faq_schema(software_type_label, industry_label, top_pick_name, software_list)

        affiliate_disclosure = (
            '<p class="affiliate-note">'
            'We may earn a commission when you purchase through our links, at no extra cost to you. '
            'Our opinions remain independent.'
            '</p>'
        )

        now = datetime.now()
        content = LIST_PAGE_TEMPLATE.substitute(
            title=title,
            meta_description=meta_description,
            software_type=software_type,
            software_type_label=software_type_label,
            software_type_slug=slugify(software_type),
            industry=row.get('industry', ''),
            industry_label=industry_label,
            industry_slug=slugify(row.get('industry', '')),
            year=year,
            date=now.strftime("%Y-%m-%d"),
            date_formatted=now.strftime("%B %Y"),
            top_rating=top_pick.get('rating', '4.0'),
            tags_yaml=", ".join(tags),
            software_list_yaml=software_list_yaml,
            affiliate_disclosure=affiliate_disclosure,
            quick_summary=quick_summary,
            trust_section=trust_section,
            comparison_table_html=comparison_table_html,
            methodology_text=methodology_text,
            software_sections_html=software_sections_html,
            who_should_consider=who_should,
            faq_section=faq_section,
            cross_links=cross_links,
            faq_schema=faq_schema,
        )

        filename = f"best-{slugify(software_type)}-for-{slugify(row.get('industry', ''))}.md"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        generated.append(filename)
        print(f"  [OK] Generated: {filename}")

    return generated


def _build_who_should_consider(top_pick, software_type_label, industry_label):
    """Editor's note on who this guide is for."""
    name = top_pick['name']
    return (
        f'<div class="who-should-section">\n'
        f'<h2>Who Should Use This Guide</h2>\n'
        f'<p>This comparison is designed for <strong>{industry_label}</strong> professionals '
        f'who are evaluating {software_type_label.lower()} tools for the first time or looking '
        f'to switch providers. Whether you are a solo practitioner, part of a growing team, or '
        f'at an established organization, our picks cover a range of budgets and use cases. '
        f'If you are specifically looking for enterprise-grade features or a free tier to start, '
        f'we call those out in each review below.</p>\n'
        f'</div>'
    )


def _build_cross_links(related_pages, current_type_label, current_industry_label):
    if not related_pages:
        return ""
    links = []
    for p in related_pages:
        type_lbl = p.get('software_type_label', p['software_type'])
        ind_lbl = p.get('industry_label', '')
        slug = slugify(p['software_type'])
        ind_slug = slugify(ind_lbl)
        links.append(f'<li><a href="/best-{slug}-for-{ind_slug}/">Best {type_lbl} for {ind_lbl}</a></li>')
    items = "\n".join(links)
    return (
        f'<div class="cross-links">\n'
        f'<h2>Related Comparisons</h2>\n'
        f'<p>See how {current_type_label.lower()} tools compare for other industries:</p>\n'
        f'<ul>{items}</ul>\n'
        f'</div>'
    )


def _build_faq(software_list, software_type_label, industry_label, top_pick_name):
    """Generate FAQ with data-driven answers."""

    # Price range
    prices = []
    for sw in software_list:
        try:
            p = sw.get('price', '0')
            p = re.sub(r'[^\d.]', '', str(p))
            prices.append(float(p))
        except (ValueError, TypeError):
            pass
    price_low = int(min(prices)) if prices else 10
    price_high = int(max(prices)) if prices else 100

    # Free plan info
    free_plan_sw = [sw for sw in software_list if sw.get('free_plan')]
    if free_plan_sw:
        free_names = ", ".join(sw['name'] for sw in free_plan_sw[:3])
        free_answer = (
            f"Yes, several tools offer free plans. "
            f"{free_names}{' and others' if len(free_plan_sw) > 3 else ''} "
            f"all have free tiers with basic features — a great way to start without commitment."
        )
    else:
        free_answer = (
            f"Most {software_type_label.lower()} tools offer free trials, but "
            f"permanent free plans are limited in this category. Look for platforms "
            f"with generous trial periods to test before buying."
        )

    # FAQ items
    faqs = [
        {
            "q": f"What is the best {software_type_label} for {industry_label}?",
            "a": (
                f"We recommend <strong>{top_pick_name}</strong> as the top choice for "
                f"{industry_label.lower()} professionals. It offers the best combination "
                f"of features, ease of use, and value — especially for teams that need "
                f"reliable performance without overpaying for unused capabilities."
            ),
        },
        {
            "q": f"Is there a free {software_type_label} for {industry_label}?",
            "a": free_answer,
        },
        {
            "q": f"How much does {software_type_label} cost for {industry_label}?",
            "a": (
                f"Pricing for {software_type_label.lower()} tools suitable for "
                f"{industry_label.lower()} typically ranges from <strong>${price_low}/mo</strong> "
                f"to <strong>${price_high}/mo</strong> per user, depending on features and "
                f"team size. Enterprise plans with advanced capabilities often cost more "
                f"but include dedicated support and custom integrations."
            ),
        },
        {
            "q": f"What should I look for in {software_type_label} for {industry_label}?",
            "a": (
                f"When choosing {software_type_label.lower()} for {industry_label.lower()}, "
                f"prioritize: ease of onboarding (your team needs to adopt it quickly), "
                f"integration with tools you already use, mobile access if you work on the go, "
                f"and scalable pricing so you are not paying for unused seats. Reading "
                f"industry-specific reviews and testing free trials before committing is always "
                f"a smart approach."
            ),
        },
    ]

    items = []
    for f in faqs:
        items.append(
            f'<div class="faq-item">'
            f'<h3>{f["q"]}</h3>'
            f'<p>{f["a"]}</p>'
            f'</div>'
        )
    return (
        f'<div class="faq-section">\n'
        f'<h2>Frequently Asked Questions</h2>\n'
        f'{"".join(items)}\n'
        f'</div>'
    )


def _build_faq_schema(software_type_label, industry_label, top_pick_name, software_list):
    """Generate FAQPage JSON-LD for rich search results."""
    top_pick = software_list[0]
    prices = []
    for sw in software_list:
        try:
            p = sw.get('price', '0')
            p = re.sub(r'[^\d.]', '', str(p))
            prices.append(float(p))
        except (ValueError, TypeError):
            pass
    price_low = int(min(prices)) if prices else 10
    price_high = int(max(prices)) if prices else 100

    free_plan_names = [sw['name'] for sw in software_list if sw.get('free_plan')]

    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"What is the best {software_type_label} for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{top_pick_name} is the top choice for {industry_label} professionals. It offers the best balance of features, ease of use, and value."
                }
            },
            {
                "@type": "Question",
                "name": f"Is there a free {software_type_label} for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{'Yes, ' + ', '.join(free_plan_names[:3]) + ' offer free plans' if free_plan_names else 'Most tools in this category offer free trials rather than permanent free plans.'}"
                }
            },
            {
                "@type": "Question",
                "name": f"How much does {software_type_label} cost for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"Prices range from ${price_low}/mo to ${price_high}/mo per user for {industry_label}-suitable plans."
                }
            },
        ]
    }

    import json
    return f'<script type="application/ld+json">\n{json.dumps(schema, indent=2)}\n</script>'


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def read_csv_data(csv_path):
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def read_yaml_data(yaml_path):
    import yaml
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_software_data(csv_path, yaml_path=None):
    yaml_data = None
    if yaml_path and os.path.exists(yaml_path):
        yaml_data = read_yaml_data(yaml_path)

    software_lookup = {}
    if yaml_data and 'software' in yaml_data:
        for sw in yaml_data['software']:
            software_lookup[sw['name'].lower()] = sw

    csv_data = None
    if csv_path and os.path.exists(csv_path):
        csv_data = read_csv_data(csv_path)

    if csv_data:
        for row in csv_data:
            software_names = row.get('software_names', '').split(';')
            enriched = []
            for name in software_names:
                name = name.strip()
                key = name.lower()
                if key in software_lookup:
                    enriched.append(software_lookup[key])
                else:
                    enriched.append({
                        'name': name,
                        'price': row.get('default_price', 'N/A'),
                        'rating': row.get('default_rating', '4.0'),
                        'best_for': row.get('industry_label', 'General'),
                        'description': f"{name} is a popular {row.get('software_type', 'software')} solution.",
                        'free_trial': row.get('default_trial', 'N/A'),
                        'free_plan': False,
                        'core_strength': 'Core functionality',
                        'features': ['Feature A', 'Feature B', 'Feature C'],
                        'pros': ['Reliable performance', 'Good support'],
                        'cons': ['Limited customization'],
                        'affiliate_url': '#',
                    })
            row['software'] = enriched
        return csv_data
    else:
        if not yaml_data:
            print("Error: No data source found.")
            sys.exit(1)
        categories = {c['id']: c for c in yaml_data.get('categories', [])}
        industries = yaml_data.get('industries', [])
        all_software = yaml_data.get('software', [])
        software_by_cat = {}
        for sw in all_software:
            cat = sw.get('category', 'other')
            software_by_cat.setdefault(cat, []).append(sw)
        pages = []
        for cat_id, cat_sw_list in software_by_cat.items():
            cat_label = categories.get(cat_id, {}).get('name', cat_id.title())
            for ind in industries:
                ind_label = ind['name']
                pages.append({
                    'software_type': cat_id,
                    'software_type_label': cat_label,
                    'industry': ind['id'],
                    'industry_label': ind_label,
                    'software': cat_sw_list[:5],
                    'count': len(cat_sw_list[:5]),
                })
        return pages


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate programmatic SEO pages for Hugo site')
    parser.add_argument('--csv', default='data/software.csv',
                        help='Path to CSV file (default: data/software.csv)')
    parser.add_argument('--yaml', default='data/software.yaml',
                        help='Path to YAML database (default: data/software.yaml)')
    parser.add_argument('--output', default='content/posts',
                        help='Output directory (default: content/posts)')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Content year (default: current)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of pages (for testing)')

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    csv_path = os.path.join(project_root, args.csv)
    yaml_path = os.path.join(project_root, args.yaml)
    output_dir = os.path.join(project_root, args.output)

    print("[DATA] Loading data...")
    if os.path.exists(csv_path):
        print(f"   CSV: {csv_path}")
    if os.path.exists(yaml_path):
        print(f"   YAML: {yaml_path}")
    print(f"[INFO] Output: {output_dir}\n")

    data = load_software_data(csv_path, yaml_path)
    print(f"[INFO] Found {len(data)} page combinations\n")

    print("[BUILD] Generating pages...")
    generated = generate_list_pages(data, output_dir, args.year, args.limit)
    print(f"\n[DONE] Generated {len(generated)} pages in {output_dir}")


if __name__ == '__main__':
    main()

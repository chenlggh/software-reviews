"""
Programmatic SEO Page Generator — Editorial Quality Edition
=============================================================
Reads software data from YAML/CSV, generates editorial-quality Markdown pages
with rich HTML structure using sentence composition, scenario analysis,
and data-rich product reviews.

Usage:
    python scripts/generate_pages.py [--csv data/software.csv] [--output content/posts]
"""

import argparse
import csv
import json
import os
import random
import re
import sys
from datetime import datetime
from string import Template


# ============================================================================
# SENTENCE BUILDING BLOCKS
# ============================================================================
# Each function group has multiple variants. Selection is data-driven:
# - Skip blocks whose data is unavailable
# - Use the first variant whose prerequisites are met
# - Fall through to a generic variant if no specific data exists

OPENING_SENTENCES = [
    # 0: strength-first (requires core_strength)
    lambda sw, ctx: (
        f"{sw['name']} ({sw.get('rating', '—')}/5) is built around "
        f"{_lower_first(sw.get('core_strength', 'core functionality'))}. "
        f"{_industry_context(sw, ctx.get('industry_label', ''))}"
    ),
    # 1: rating-first
    lambda sw, ctx: (
        f"With a {sw.get('rating', '—')}/5 rating, {sw['name']} focuses on "
        f"{_lower_first(sw.get('core_strength', 'core functionality'))}. "
        f"This matters for {_lower_first(ctx.get('industry_label', 'teams'))} because "
        f"{_industry_context(sw, ctx.get('industry_label', ''), lower=True)}"
    ),
    # 2: audience-first (requires best_for)
    lambda sw, ctx: (
        f"Designed for {_lower_first(sw.get('best_for', 'general use'))}, "
        f"{sw['name']} delivers {_lower_first(sw.get('core_strength', 'reliable performance'))} "
        f"that {_lower_first(ctx.get('industry_label', 'teams'))} teams rely on daily."
    ),
    # 3: comparison-opener (requires a data_point)
    lambda sw, ctx: (
        f"In the {_lower_first(ctx.get('category_label', 'software'))} space, "
        f"{sw['name']} differentiates itself through "
        f"{_lower_first(sw.get('core_strength', 'its core capabilities'))}. "
        f"{_industry_context(sw, ctx.get('industry_label', ''))}"
    ),
]

STRENGTH_SENTENCES = [
    # 0: pro-detail (requires extended_pros)
    lambda sw, ctx: (
        f"The standout feature is {_lower_first(sw['extended_pros'][0]['summary'])}: "
        f"{_lower_first(sw['extended_pros'][0]['detail'])}"
    ) if sw.get('extended_pros') else None,
    # 1: metric-highlight (requires data_points)
    lambda sw, ctx: (
        f"On metrics that matter for {_lower_first(ctx.get('industry_label', 'teams'))}, "
        f"{sw['name']} delivers {sw['data_points'][0]['value']} in "
        f"{sw['data_points'][0]['metric']}. "
        f"{sw['data_points'][0].get('context', '')}"
    ) if sw.get('data_points') else None,
    # 2: integration-angle (requires key_integrations)
    lambda sw, ctx: (
        f"With support for {', '.join(sw['key_integrations'][:3])} and more, "
        f"{sw['name']} connects with the tools "
        f"{_lower_first(ctx.get('industry_label', 'teams'))} teams already use."
    ) if sw.get('key_integrations') else None,
    # 3: user-feedback (requires review_highlights)
    lambda sw, ctx: (
        f"Users on {sw['review_highlights'][0]['source']} rate "
        f"{sw['name']} {sw['review_highlights'][0]['rating']}/5, noting "
        f"that \"{_lower_first(sw['review_highlights'][0]['snippet'])}\"."
    ) if sw.get('review_highlights') else None,
    # 4: generic pro (fallback)
    lambda sw, ctx: (
        f"{sw['name']} earns strong marks for "
        f"{_lower_first(sw['pros'][0]) if sw.get('pros') else 'overall reliability'}."
    ),
]

DRAWBACK_SENTENCES = [
    # 0: con-detail (requires extended_cons)
    lambda sw, ctx: (
        f"On the downside, {_lower_first(sw['extended_cons'][0]['summary'])} is a concern: "
        f"{_lower_first(sw['extended_cons'][0]['detail'])}"
    ) if sw.get('extended_cons') else None,
    # 1: con-comparison (requires extended_cons with detail)
    lambda sw, ctx: (
        f"Compared to competitors, {sw['name']} falls short on "
        f"{_lower_first(sw['extended_cons'][0]['summary'])}. "
        f"{_lower_first(sw['extended_cons'][0]['detail'])}"
    ) if sw.get('extended_cons') else None,
    # 2: con-scenario (requires not_ideal_for_scenarios)
    lambda sw, ctx: (
        f"This becomes a limitation when "
        f"{_lower_first(sw['not_ideal_for_scenarios'][0])}."
    ) if sw.get('not_ideal_for_scenarios') else None,
    # 3: generic con (fallback)
    lambda sw, ctx: (
        f"The most common criticism is "
        f"{_lower_first(sw['cons'][0]) if sw.get('cons') else 'a learning curve for new users'}."
    ),
]

AUDIENCE_SENTENCES = [
    # 0: ideal-scenario (requires ideal_for_scenarios)
    lambda sw, ctx: (
        f"Best suited when "
        f"{_lower_first(sw['ideal_for_scenarios'][0])}."
    ) if sw.get('ideal_for_scenarios') else None,
    # 1: not-for (requires not_ideal_for_scenarios)
    lambda sw, ctx: (
        f"Less ideal if "
        f"{_lower_first(sw['not_ideal_for_scenarios'][0])}."
    ) if sw.get('not_ideal_for_scenarios') else None,
    # 2: pricing-angle (requires pricing_tiers)
    lambda sw, ctx: (
        f"At {sw['pricing_tiers'][0]['price']}/mo starting, "
        f"{sw['name']} fits {_lower_first(sw.get('best_for', 'general business use'))} "
        f"that need {_lower_first(sw.get('core_strength', 'reliable performance'))}."
    ) if sw.get('pricing_tiers') else None,
    # 3: generic audience
    lambda sw, ctx: (
        f"Recommended for {_lower_first(sw.get('best_for', 'general business use'))} "
        f"evaluating {_lower_first(ctx.get('category_label', 'software'))} solutions."
    ),
]

BUYING_GUIDE_CRITERIA = {
    "crm": "Sales process alignment — lead-to-close workflow should match your actual sales cycle without forcing you to adapt",
    "project-management": "Project complexity — match the tool's workflow depth to the complexity of your projects, not the other way around",
    "invoicing": "Invoice volume — tools vary significantly in batch processing, recurring billing, and payment gateway support",
    "email-marketing": "List growth trajectory — choose a platform whose pricing scales with your contact list, not one that penalizes growth",
    "accounting": "Tax and compliance needs — ensure the platform supports your business structure (LLC, S-Corp, nonprofit) and tax filing requirements",
}


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text


def _lower_first(s):
    """Lowercase the first character of a string. Handles acronyms (CRM → CRM, not cRM)."""
    s = s.strip()
    if not s:
        return s
    # Don't lowercase if the first two chars are uppercase (likely an acronym)
    if len(s) >= 2 and s[0].isupper() and s[1].isupper():
        return s
    return s[0].lower() + s[1:] if s else s


def _upper_first(s):
    """Uppercase the first character of a string."""
    s = s.strip()
    return s[0].upper() + s[1:] if s else s


def _lower_all(s):
    """Lowercase all words in a phrase for mid-sentence use."""
    return s.strip().lower()


def _ensure_text(text):
    """Clean up a text snippet: lowercase-ish first."""
    text = text.strip()
    return text[0].lower() + text[1:] if text else text


def _ensure_clause(text):
    """Make a summary fit after 'the main trade-off is'. Returns a readable noun phrase."""
    text = text.strip()
    # Verb phrase start: "Can get expensive..." → "that it can get expensive..."
    verb_starts = ('can ', 'may ', 'does ', 'could ', 'might ', 'will ', 'would ', 'shall ', 'should ')
    for v in verb_starts:
        if text.lower().startswith(v):
            return f"that it {_ensure_text(text)}"
    # UI/UX phrases: "UI can feel..." → "that the UI can feel..."
    ui_starts = ('ui ', 'ux ', 'app ', 'api ')
    for v in ui_starts:
        if text.lower().startswith(v):
            return f"that the {_ensure_text(text)}"
    # Generic adjective or noun start: "Steep learning curve" → "that it has {text}"
    return f"that {_ensure_text(text)}"


def _ensure_period(text):
    """Ensure text ends with a sentence-ending punctuation mark."""
    text = text.strip()
    if not text:
        return text
    if not text[-1] in ('.', '!', '?'):
        text += '.'
    return text


def _industry_context(sw, industry_label, lower=False):
    """Get the industry context sentence for a software product."""
    industry_key = slugify(industry_label.replace('-', ' '))
    ctx = sw.get('industry_context', {})
    for key in [industry_label.lower().replace(' ', '-'), industry_label.lower().replace(' ', '_'), slugify(industry_label)]:
        if key in ctx and ctx[key]:
            txt = ctx[key].strip()
            return _upper_first(txt) if not lower else txt
    return f"A strong option for {_lower_first(industry_label)} teams evaluating {_lower_first(sw.get('core_strength', 'software tools'))}."


def _pick_variant(variants, sw, ctx, default_index=-1):
    """Try each variant in order. Return first non-None result."""
    for i, variant in enumerate(variants):
        result = variant(sw, ctx)
        if result is not None:
            return result
    return variants[default_index](sw, ctx) if default_index >= 0 else ""


# ============================================================================
# PRODUCT SELECTION
# ============================================================================

def select_products_for_page(page_category, page_industry, all_products, max_products=5):
    """
    Score and rank products by category match and industry relevance.
    Primary category = 100 pts, also_suitable_for = 50 pts.
    Industry context available = +30 pts. Rating bonus = rating * 10.
    """
    scored = []
    for product in all_products:
        score = 0

        # Category match
        cat = product.get('category', '')
        also = product.get('also_suitable_for', [])
        if cat == page_category:
            score += 100
        elif page_category in also:
            score += 50
        else:
            continue  # exclude if no category match

        # Industry relevance bonus
        ctx = product.get('industry_context', {})
        for key in ctx:
            if isinstance(key, str) and (slugify(key) == slugify(page_industry) or
                                         slugify(key.replace('-', ' ')) == slugify(page_industry)):
                if ctx[key]:
                    score += 30
                break

        # Rating bonus (tiebreaker)
        try:
            score += float(product.get('rating', 0)) * 10
        except (ValueError, TypeError):
            pass

        scored.append((score, product))

    scored.sort(key=lambda x: -x[0])
    return [p[1] for p in scored[:max_products]]


# ============================================================================
# HTML BUILDERS
# ============================================================================

def build_review_paragraphs(sw, rank, ctx):
    """
    Generate 2-4 paragraphs for a single product review using sentence composition.
    Paragraph count depends on available data.
    """
    paragraphs = []

    # Paragraph 1: Opening (always)
    opening = _pick_variant(OPENING_SENTENCES, sw, ctx)
    paragraphs.append(f'<p>{_ensure_period(opening)}</p>')

    # Paragraph 2: Strength / metric / integration (always)
    strength = _pick_variant(STRENGTH_SENTENCES, sw, ctx)
    paragraphs.append(f'<p>{_ensure_period(strength)}</p>')

    # Paragraph 3: Data point callout (conditional — only if data_points exist)
    if sw.get('data_points') and len(sw['data_points']) > 1:
        dp = sw['data_points'][1]
        dp_text = f"For context, {sw['name']} reports \"{dp['value']}\" in {dp['metric']}."
        if dp.get('context'):
            dp_text += f" {_upper_first(dp['context'])}."
        paragraphs.append(f'<p>{dp_text}</p>')

    # Paragraph 4: Drawback (conditional — only if cons exist)
    if sw.get('extended_cons') or sw.get('cons'):
        drawback = _pick_variant(DRAWBACK_SENTENCES, sw, ctx)
        paragraphs.append(f'<p>{_ensure_period(drawback)}</p>')

    # Paragraph 5: Audience closing (always)
    audience = _pick_variant(AUDIENCE_SENTENCES, sw, ctx, default_index=3)
    paragraphs.append(f'<p>{_ensure_period(audience)}</p>')

    return paragraphs


def format_extended_pros_html(pros):
    """Build extended pros as summary+detail cards."""
    if not pros:
        return ""
    items = []
    for p in pros[:4]:
        items.append(
            f'<div class="pro-card">'
            f'<span class="pro-card__summary">{_upper_first(p["summary"])}</span>'
            f'<p class="pro-card__detail">{_upper_first(p["detail"])}</p>'
            f'</div>'
        )
    return f'<div class="extended-pros">{"".join(items)}</div>'


def format_extended_cons_html(cons):
    """Build extended cons as summary+detail cards."""
    if not cons:
        return ""
    items = []
    for c in cons[:3]:
        items.append(
            f'<div class="con-card">'
            f'<span class="con-card__summary">{_upper_first(c["summary"])}</span>'
            f'<p class="con-card__detail">{_upper_first(c["detail"])}</p>'
            f'</div>'
        )
    return f'<div class="extended-cons">{"".join(items)}</div>'


def format_integration_tags(integrations):
    """Build integration tag pills."""
    if not integrations:
        return ""
    pills = "".join(f'<span class="integration-tag">{i}</span>' for i in integrations[:6])
    return f'<div class="integration-tags"><strong>Integrations:</strong> {pills}</div>'


def format_comparison_table_html(software_list, top_pick_name):
    """Build an HTML comparison table with G2 rating and free plan columns."""
    rows = []
    for i, sw in enumerate(software_list):
        is_top = sw['name'] == top_pick_name
        tr_class = ' class="top-pick-row"' if is_top else ""
        star = ' ★' if is_top else ''
        free_plan = "Yes" if sw.get('free_plan') else "—"
        g2 = sw.get('g2_rating', '')
        g2_str = f"{g2}/5" if g2 else "—"
        rows.append(
            f'<tr{tr_class}>'
            f'<td class="col-rank">{i + 1}{star}</td>'
            f'<td class="col-name">{sw["name"]}</td>'
            f'<td class="col-price">{sw.get("price", "—")}</td>'
            f'<td class="col-trial">{sw.get("free_trial", "—") or "—"}</td>'
            f'<td class="col-g2">{g2_str}</td>'
            f'<td class="col-plan">{free_plan}</td>'
            f'<td class="col-rating"><span class="rating-badge">{sw.get("rating", "—")}/5</span></td>'
            f'</tr>'
        )
    header = (
        '<thead>'
        '<tr><th>#</th><th>Software</th><th>Starting Price</th>'
        '<th>Free Trial</th><th>G2 Rating</th><th>Free Plan</th><th>Rating</th></tr>'
        '</thead>'
    )
    return f'<div class="table-wrapper"><table class="comparison-table">{header}<tbody>{"".join(rows)}</tbody></table></div>'


def build_software_card_html(rank, sw, ctx):
    """Build one software review as an HTML card with multiple paragraphs."""
    name = sw['name']
    rating = sw.get('rating', '—')
    core_strength = sw.get('core_strength', '')
    best_for = sw.get('best_for', 'General')
    paragraphs = build_review_paragraphs(sw, rank, ctx)
    extended_pros_html = format_extended_pros_html(sw.get('extended_pros', []))
    extended_cons_html = format_extended_cons_html(sw.get('extended_cons', []))
    integrations_html = format_integration_tags(sw.get('key_integrations', []))

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

    # Combine paragraphs
    paragraphs_html = "\n    ".join(paragraphs)

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

  <div class="software-review__text">
    {paragraphs_html}
  </div>

  <div class="software-review__grid">
    <div class="software-review__detail"><strong>Best for:</strong> {best_for}</div>
    <div class="software-review__detail"><strong>Core strength:</strong> {core_strength}</div>
  </div>

  {integrations_html}

  <div class="software-review__details">
    <div class="software-review__pros-cons">
      <div class="pros-column">
        <h4 class="pros-heading">What we like</h4>
        {extended_pros_html}
      </div>
      <div class="cons-column">
        <h4 class="cons-heading">What could improve</h4>
        {extended_cons_html}
      </div>
    </div>
  </div>

  <a href="{url}" class="review-cta" rel="sponsored nofollow" target="_blank">Visit {name} →</a>
</div>"""


# ============================================================================
# SECTION GENERATORS
# ============================================================================

def generate_scenario_analysis(software_list, ctx):
    """Generate 'Choose X if... vs Consider Y instead' scenario analysis."""
    if len(software_list) < 2:
        return ""

    top = software_list[0]
    sections = []

    # Top pick scenario
    top_scenarios = top.get('ideal_for_scenarios', [])
    top_reason = top_scenarios[0] if top_scenarios else f"Need {_lower_first(top.get('core_strength', 'core functionality'))}"
    sections.append(
        f'<div class="scenario-item scenario-item--choose">'
        f'<h3>Choose {top["name"]} if…</h3>'
        f'<p>{_upper_first(top_reason)}.</p>'
        f'</div>'
    )

    # Second pick alternative
    second = software_list[1]
    second_scenarios = second.get('ideal_for_scenarios', [])
    second_reason = second_scenarios[0] if second_scenarios else f"Prefer {_lower_first(second.get('core_strength', 'a different approach'))}"
    sections.append(
        f'<div class="scenario-item scenario-item--consider">'
        f'<h3>Consider {second["name"]} instead if…</h3>'
        f'<p>{_upper_first(second_reason)}.</p>'
        f'</div>'
    )

    # Bottom pick skip scenario
    if len(software_list) >= 3:
        bottom = software_list[-1]
        bottom_not_ideal = bottom.get('not_ideal_for_scenarios', [])
        if bottom_not_ideal:
            bottom_reason = bottom_not_ideal[0]
        elif bottom.get('extended_cons'):
            bottom_reason = bottom['extended_cons'][0]['summary']
        else:
            bottom_reason = f"Limitations in {_lower_first(bottom.get('core_strength', 'capabilities'))}"

        sections.append(
            f'<div class="scenario-item scenario-item--skip">'
            f'<h3>Skip {bottom["name"]} when…</h3>'
            f'<p>{_upper_first(bottom_reason)}.</p>'
            f'</div>'
        )

    return (
        f'<div class="scenario-analysis">\n'
        f'<h2>Quick Decision Guide</h2>\n'
        f'<p>Not sure which {_lower_all(ctx.get("category_label", "software"))} tool fits your '
        f'{_lower_all(ctx.get("industry_label", "needs"))}? Here is our take.</p>\n'
        f'{"".join(sections)}\n'
        f'</div>'
    )


def generate_buying_guide(ctx):
    """Generate industry-specific buying criteria section."""
    cat = ctx.get('software_type', '')
    industry = ctx.get('industry_label', '')
    criteria_text = BUYING_GUIDE_CRITERIA.get(cat, "Features that directly impact daily workflows and team adoption")

    return (
        f'<div class="buying-guide">\n'
        f'<h2>What to Look for in {ctx.get("category_label", "Software")} for {industry}</h2>\n'
        f'<ol class="buying-guide__list">\n'
        f'  <li class="buying-guide__item">'
        f'<strong>Start with your workflow, not the features list.</strong> '
        f'The best tool is the one that fits your {_lower_first(industry)} '
        f'team\'s actual process. {criteria_text}.</li>\n'
        f'  <li class="buying-guide__item">'
        f'<strong>Check integration compatibility.</strong> '
        f'Make sure the tool connects with the software your team already uses. '
        f'The tools in this comparison offer between 100 and 7,000+ integrations depending on the platform.</li>\n'
        f'  <li class="buying-guide__item">'
        f'<strong>Test with your own data.</strong> '
        f'Most tools in this comparison offer free trials or free tiers. '
        f'Testing with real workflows beats reading feature comparisons every time.</li>\n'
        f'  <li class="buying-guide__item">'
        f'<strong>Plan for growth.</strong> '
        f'Consider not just your current team size but where you will be in 12-24 months. '
        f'Migrating platforms later is more expensive than starting with room to grow.</li>\n'
        f'</ol>\n'
        f'</div>'
    )


def get_related_pages(current_type, current_industry, all_pages, max_links=3):
    """Find related pages: same type diff industry, then same industry diff type."""
    related = []
    type_matches = [p for p in all_pages if p['software_type'] == current_type and p['industry'] != current_industry]
    industry_matches = [p for p in all_pages if p['industry'] == current_industry and p['software_type'] != current_type]
    combined = type_matches + industry_matches
    seen = set()
    for p in combined:
        key = f"{p['software_type']}-{p['industry']}"
        if key not in seen:
            seen.add(key)
            related.append(p)
    return related[:max_links]


def build_faq(software_list, ctx, top_pick_name):
    """Generate FAQ with data-driven answers using pricing tiers and specific data."""
    category_label = ctx.get('category_label', 'Software')
    industry_label = ctx.get('industry_label', '')

    # Price range from pricing_tiers
    prices = []
    for sw in software_list:
        tiers = sw.get('pricing_tiers', [])
        for t in tiers:
            try:
                p = re.sub(r'[^\d.]', '', t['price'])
                if p:
                    prices.append(float(p))
            except (ValueError, TypeError):
                pass
        # Fallback to price field
        if not tiers:
            try:
                p = re.sub(r'[^\d.]', '', str(sw.get('price', '0')))
                if p:
                    prices.append(float(p))
            except (ValueError, TypeError):
                pass

    price_low = int(min(prices)) if prices else 0
    price_high = int(max(prices)) if prices else 0

    # Free plan info
    free_plan_sw = [sw for sw in software_list if sw.get('free_plan')]
    if free_plan_sw:
        free_names = []
        for sw in free_plan_sw[:3]:
            tiers = sw.get('pricing_tiers', [])
            free_tier = next((t for t in tiers if t['price'] == '$0' or t['tier'].lower() == 'free'), None)
            limit_info = f" ({free_tier['limits']})" if free_tier else ""
            free_names.append(f"{sw['name']}{limit_info}")
        free_answer = (
            f"Yes. {', '.join(free_names[:-1])}{' and ' if len(free_names) > 1 else ''}"
            f"{free_names[-1] if free_names else ''} offer free plans "
            f"with basic features — enough to evaluate the platform without financial commitment."
        )
    else:
        free_answer = (
            f"Most {_lower_first(category_label)} tools offer free trials (typically 14-30 days), "
            f"but permanent free plans are uncommon in this category. "
            f"Use the trial periods to test with real workflows before purchasing."
        )

    # Top pick pricing detail
    top_pick = software_list[0]
    top_tiers = top_pick.get('pricing_tiers', [])
    if top_tiers and len(top_tiers) > 1:
        paid_tier = top_tiers[1]
        top_pricing_detail = (
            f"{top_pick_name} starts with a {top_tiers[0]['tier']} plan at "
            f"{top_tiers[0]['price']}/mo ({top_tiers[0]['limits']}). "
            f"The {paid_tier['tier']} plan at {paid_tier['price']}/mo "
            f"unlocks {paid_tier['limits']}."
        )
    else:
        top_pricing_detail = (
            f"{top_pick_name} starts at {top_pick.get('price', 'contact for pricing')}."
        )

    # Integration breadth
    top_ints = top_pick.get('key_integrations', [])
    int_detail = ", ".join(top_ints[:4]) if top_ints else "various third-party services"

    faqs = [
        {
            "q": f"What is the best {category_label} for {industry_label}?",
            "a": (
                f"Based on our testing across {len(software_list)} platforms, "
                f"<strong>{top_pick_name}</strong> is the top choice for "
                f"{_lower_first(industry_label)} professionals. "
                f"{top_pick.get('ideal_for_scenarios', [top_pick.get('best_for', 'its combination of features and value')])[0]}."
            ),
        },
        {
            "q": f"Is there a free {category_label} for {industry_label}?",
            "a": free_answer,
        },
        {
            "q": f"How much does {category_label} cost for {industry_label}?",
            "a": (
                f"Pricing for {_lower_first(category_label)} tools suitable for "
                f"{_lower_first(industry_label)} ranges from "
                f"<strong>${price_low}/mo</strong> to <strong>${price_high}/mo</strong> "
                f"per user. {top_pricing_detail}"
            ),
        },
        {
            "q": f"What should I look for when choosing {category_label} for {industry_label}?",
            "a": (
                f"Start with team size and workflow complexity. Smaller teams benefit from ease of use "
                f"and fast onboarding (Pipedrive, Trello, Wave). Growing organizations need scalability, "
                f"customization, and integration depth (Salesforce, Asana, QuickBooks). "
                f"Always test with a free trial using your own data before committing."
            ),
        },
        {
            "q": f"How do the top {category_label} platforms compare on integrations?",
            "a": (
                f"{top_pick_name} leads with support for {int_detail}. "
                f"Integration breadth varies significantly — enterprise platforms like Salesforce offer "
                f"7,000+ AppExchange apps, while simpler tools focus on the most common connectors. "
                f"Check that your essential tools (email, calendar, accounting) are supported before purchasing."
            ),
        },
        {
            "q": f"Can I use multiple {category_label} tools together?",
            "a": (
                f"Yes. Many teams use a primary platform for core operations and supplement with "
                f"specialized tools — for example, using HubSpot for CRM and Mailchimp for email campaigns, "
                f"or QuickBooks for accounting while FreshBooks handles invoicing. "
                f"Integration tools like Zapier connect them without manual data transfer."
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


def build_faq_schema(category_label, industry_label, top_pick_name, software_list):
    """Generate FAQPage JSON-LD for rich search results — 5 questions."""
    prices = []
    for sw in software_list:
        try:
            p = re.sub(r'[^\d.]', '', str(sw.get('price', '0')))
            if p:
                prices.append(float(p))
        except (ValueError, TypeError):
            pass
    price_low = int(min(prices)) if prices else 0
    price_high = int(max(prices)) if prices else 0

    free_plan_names = [sw['name'] for sw in software_list if sw.get('free_plan')]

    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"What is the best {category_label} for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{top_pick_name} is the top choice for {industry_label}. It offers the best balance of features, ease of use, and value for this audience."
                }
            },
            {
                "@type": "Question",
                "name": f"Is there a free {category_label} for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{'Yes, ' + ', '.join(free_plan_names[:3]) + ' offer free plans' if free_plan_names else 'Most tools offer free trials rather than permanent free plans.'}"
                }
            },
            {
                "@type": "Question",
                "name": f"How much does {category_label} cost for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"Prices range from ${price_low}/mo to ${price_high}/mo per user. Enterprise plans with advanced features cost more."
                }
            },
            {
                "@type": "Question",
                "name": f"What should I look for in {category_label} for {industry_label}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"Prioritize ease of onboarding, integration with existing tools, mobile access, and pricing that scales with your team size."
                }
            },
            {
                "@type": "Question",
                "name": f"Which {category_label} is best for small {industry_label} teams?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"For small teams in {industry_label}, look for free tiers or affordable pricing, quick setup, and essential features without enterprise complexity."
                }
            },
        ]
    }

    return f'<script type="application/ld+json">\n{json.dumps(schema, indent=2)}\n</script>'


# ============================================================================
# PAGE TEMPLATE
# ============================================================================

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

## Quick Decision Guide

$scenario_analysis

## Detailed Reviews

$software_sections_html

$buying_guide

$faq_section

$cross_links

---

*Last updated: $date_formatted*

$faq_schema
""")


# ============================================================================
# METHODOLOGY TEMPLATES
# ============================================================================

METHODOLOGY_TEMPLATES = {
    "crm": (
        "To evaluate {count} {label} platforms, we focused on criteria that matter most "
        "for day-to-day sales and marketing work: contact management depth, deal tracking "
        "capabilities, integration ecosystem, email marketing features, and mobile app quality. "
        "We tested free trials, analyzed G2 and Capterra reviews, and spoke with sales ops "
        "professionals to validate our findings. For {industry} specifically, we also evaluated "
        "{industry_criterion}."
    ),
    "project-management": (
        "Our evaluation of {count} {label} tools centered on how well they help teams "
        "stay organized: task management flexibility, collaboration features, reporting "
        "capabilities, third-party integrations, and ease of onboarding. We built real "
        "projects in each tool, tested automation features, and reviewed user feedback "
        "from verified buyers. For {industry} teams, we paid special attention to "
        "{industry_criterion}."
    ),
    "invoicing": (
        "We compared {count} {label} solutions by looking at what freelancers and small "
        "businesses actually need: invoice customization, payment processing speed, "
        "expense tracking, time tracking integration, and accounting report quality. "
        "Each tool was tested with real invoice workflows and reviewed for pricing transparency. "
        "Our {industry} evaluation focused on {industry_criterion}."
    ),
    "email-marketing": (
        "Our team tested {count} {label} platforms across the metrics that drive campaign "
        "success: email deliverability, template quality, automation capabilities, list "
        "management tools, and analytics depth. We sent test campaigns, evaluated segmentation "
        "features, and analyzed deliverability rates across major providers. "
        "For {industry} use cases, we emphasized {industry_criterion}."
    ),
    "accounting": (
        "We reviewed {count} {label} tools using criteria that matter for financial accuracy: "
        "bookkeeping features, tax preparation support, bank reconciliation ease, payroll "
        "integration, and reporting depth. Each tool was evaluated for both small business "
        "and freelancer use cases. Our {industry} review prioritized {industry_criterion}."
    ),
}

DEFAULT_METHODOLOGY = (
    "We evaluated {count} {label} platforms based on feature set, ease of use, pricing, "
    "customer support, and integration capabilities. We analyzed user reviews from G2 and "
    "Capterra, tested free trials where available, and consulted industry experts to ensure "
    "our recommendations are unbiased and data-driven."
)

INDUSTRY_CRITERIA = {
    "real-estate": "property-centric features such as listing tracking, territory management, and client communication tools",
    "freelancers": "pricing flexibility, solo-user experience, and the ability to manage multiple client relationships efficiently",
    "small-business": "ease of adoption, affordable scaling, and out-of-the-box functionality that doesn't require dedicated admin staff",
    "startups": "speed of setup, team collaboration features, and pricing that doesn't penalize early-stage growth",
    "enterprise": "advanced security, compliance certifications, API depth, and the ability to handle complex organizational structures",
    "nonprofits": "donor or grant management capabilities, nonprofit pricing discounts, and reporting suitable for funders",
    "construction": "project-based workflows, milestone tracking, and subcontractor or supply chain coordination features",
    "healthcare": "HIPAA compliance readiness, patient or referral tracking, and secure communication capabilities",
    "ecommerce": "e-commerce platform integrations, order-to-cash pipeline support, and customer segmentation tools",
    "education": "student or enrollment pipeline management, academic calendar alignment, and multi-department collaboration",
}


# ============================================================================
# MAIN GENERATION
# ============================================================================

def generate_list_pages(data, output_dir, year=None, limit=None, all_products=None):
    if year is None:
        year = datetime.now().year
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    for i, row in enumerate(data):
        if limit and i >= limit:
            break

        software_type = row['software_type']
        software_type_label = row.get('software_type_label', software_type.title())
        industry_raw = row.get('industry', '')
        industry_label = row.get('industry_label', '')

        # Select products using scoring algorithm
        if all_products:
            software_list = select_products_for_page(software_type, industry_raw, all_products)
        else:
            software_list = row.get('software', [])

        count = len(software_list)
        if count == 0:
            continue

        top_pick = software_list[0]
        top_pick_name = top_pick['name']

        ctx = {
            'software_type': software_type,
            'category_label': software_type_label,
            'industry': industry_raw,
            'industry_label': industry_label,
        }

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
            f'professionals. {top_pick.get("ideal_for_scenarios", ["It offers the strongest balance of features, usability, and value in this category."])[0]}'
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
        industry_criterion = INDUSTRY_CRITERIA.get(industry_raw, "industry-specific workflow requirements")
        methodology_text = method_template.format(
            count=count,
            label=software_type_label,
            industry=industry_label,
            industry_criterion=industry_criterion
        )

        # --- Scenario analysis ---
        scenario_analysis = generate_scenario_analysis(software_list, ctx)

        # --- Software review cards ---
        software_cards = []
        for rank, sw in enumerate(software_list, 1):
            card = build_software_card_html(rank, sw, ctx)
            software_cards.append(card)
        software_sections_html = "\n".join(software_cards)

        # --- Buying guide ---
        buying_guide = generate_buying_guide(ctx)

        # --- FAQ ---
        faq_section = build_faq(software_list, ctx, top_pick_name)

        # --- Cross links ---
        related_pages = get_related_pages(software_type, industry_raw, data)
        cross_links = _build_cross_links(related_pages, software_type_label, industry_label)

        # --- FAQ schema (JSON-LD) ---
        faq_schema = build_faq_schema(software_type_label, industry_label, top_pick_name, software_list)

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
            industry=industry_raw,
            industry_label=industry_label,
            industry_slug=slugify(industry_raw),
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
            scenario_analysis=scenario_analysis,
            software_sections_html=software_sections_html,
            buying_guide=buying_guide,
            faq_section=faq_section,
            cross_links=cross_links,
            faq_schema=faq_schema,
        )

        # Generate filename from the industry slug, preserving existing URL structure
        filename = f"best-{slugify(software_type)}-for-{slugify(industry_raw)}.md"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        generated.append(filename)
        print(f"  [OK] Generated: {filename}")

    return generated


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
        f'<p>See how {_lower_first(current_type_label)} tools compare for other industries:</p>\n'
        f'<ul>{items}</ul>\n'
        f'</div>'
    )


# ============================================================================
# DATA LOADING
# ============================================================================

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

    all_products = list(software_lookup.values()) if software_lookup else []

    if csv_data:
        for row in csv_data:
            # Use scoring-based product selection from YAML data
            software_names = row.get('software_names', '').split(';')
            enriched = []
            for name in software_names:
                name = name.strip()
                key = name.lower()
                if key in software_lookup:
                    enriched.append(software_lookup[key])
                else:
                    # Fallback for products not in YAML
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
        return csv_data, all_products
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
        return pages, all_products


# ============================================================================
# CLI
# ============================================================================

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

    data, all_products = load_software_data(csv_path, yaml_path)
    print(f"[INFO] Found {len(data)} page combinations, {len(all_products)} products\n")

    print("[BUILD] Generating pages with editorial-quality engine...")
    generated = generate_list_pages(data, output_dir, args.year, args.limit, all_products)
    print(f"\n[DONE] Generated {len(generated)} pages in {output_dir}")


if __name__ == '__main__':
    main()

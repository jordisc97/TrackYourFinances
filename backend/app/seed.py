import secrets

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Category, CategoryRule, Household


DEFAULT_CATEGORIES = [
    ("Housing", "expense", "#8B5E3C"),
    ("Utilities", "expense", "#4A6FA5"),
    ("Groceries", "expense", "#C45C26"),
    ("Dining & Takeaway", "expense", "#E76F51"),
    ("Transportation", "expense", "#3D5A80"),
    ("Health", "expense", "#2A9D8F"),
    ("Personal Care", "expense", "#E9C46A"),
    ("Clothing & Footwear", "expense", "#9B5DE5"),
    ("Electronics & Home Goods", "expense", "#577590"),
    ("Subscriptions", "expense", "#6D597A"),
    ("Entertainment & Leisure", "expense", "#F4A261"),
    ("Travel", "expense", "#264653"),
    ("Childcare/Education", "expense", "#43AA8B"),
    ("Pets", "expense", "#F9844A"),
    ("Gifts & Donations", "expense", "#F72585"),
    ("Bank & Financial Fees", "expense", "#495057"),
    ("One-off Large Purchases", "expense", "#6B7C5E"),
    ("Transfer", "transfer", "#7A7A7A"),
    ("Income", "income", "#2D6A4F"),
    ("Investment", "investment", "#1B4332"),
]

# (category_name, pattern, match_type, priority) — ES/EU merchants first.
DEFAULT_CATEGORY_RULES = [
    ("Housing", r"\b(alquiler|rent|mortgage|hipoteca|home\s*insur|seguro\s*hogar|ikea|leroy\s*merlin|bauhaus)\b", "regex", 20),
    ("Utilities", r"\b(endesa|iberdrola|naturgy|repsol\s*gas|canal\s*isabel|aguas|vodafone|movistar|orange|digi|pepephone|electricidad|gas\s*natural)\b", "regex", 20),
    ("Groceries", r"\b(mercadona|carrefour|lidl|aldi|dia\b|eroski|consum|hipercor|el\s*corte\s*ingles\s*super|supermercado|butcher|carnicer|panader|bakery)\b", "regex", 20),
    ("Dining & Takeaway", r"\b(glovo|just\s*eat|uber\s*eats|deliveroo|mcdonald|burger\s*king|kfc|starbucks|restaurant|restaurante|cafe|cafeteria|bar\s+|pub\b|takeaway)\b", "regex", 20),
    ("Transportation", r"\b(uber(?!\s*eats)|cabify|bolt|renfe|metro|emt|tmb|parking|gasolin|repsol\s*estaciones|cepsa|bp\s+|shell\b|toll|peaje|abus|car\s*insur|seguro\s*auto)\b", "regex", 20),
    ("Health", r"\b(farmacia|pharmacy|doctor|dentist|dentista|optica|optician|sanitas|adeslas|dkv|gym|gimnasio|basic.?fit|fitness)\b", "regex", 20),
    ("Personal Care", r"\b(peluquer|haircut|barber|skincare|primor|sephora|druni|toiletries|cosmetics|perfumer)\b", "regex", 20),
    ("Clothing & Footwear", r"\b(zara|h&m|hm\b|mango|uniqlo|nike|adidas|decathlon|primark|footlocker|sprinter|massimo\s*dutti)\b", "regex", 20),
    ("Electronics & Home Goods", r"\b(media\s*markt|fnac|amazon|pccomponentes|apple\s*store|samsung|xiaomi|electronics|gadget)\b", "regex", 25),
    ("Subscriptions", r"\b(netflix|spotify|disney\+|disneyplus|hbo|max\b|amazon\s*prime|youtube\s*premium|icloud|google\s*one|dropbox|openai|chatgpt|microsoft\s*365|adobe|notion|github)\b", "regex", 15),
    ("Entertainment & Leisure", r"\b(cinema|cine\b|concert|concierto|ticketmaster|entradas|steam|playstation|xbox|hobby|museo|museum)\b", "regex", 25),
    ("Travel", r"\b(ryanair|vueling|iberia|airbnb|booking\.com|hotel|hostel|expedia|travel\s*insur|seguro\s*viaje|flight|vuelo)\b", "regex", 20),
    ("Childcare/Education", r"\b(colegio|school|guarderia|childcare|universidad|udemy|coursera|tuition|matricula)\b", "regex", 20),
    ("Pets", r"\b(veterinar|vet\b|pet\s*shop|tiendanimal|kiwoko|zooplus|dog\s*food|cat\s*food|grooming)\b", "regex", 20),
    ("Gifts & Donations", r"\b(donaci[oó]n|donation|charity|ong\b|cruz\s*roja|unicef|regalo|gift\b)\b", "regex", 30),
    ("Bank & Financial Fees", r"\b(comisi[oó]n|fee\b|interest|inter[eé]s|loan\s*repay|prestamo|descubierto|card\s*fee)\b", "regex", 20),
    ("One-off Large Purchases", r"\b(renovation|reforma|muebles\s*grandes|big\s*ticket)\b", "regex", 40),
    ("Transfer", r"\b(transferencia|traspaso|bizum|internal\s*transfer|own\s*account)\b", "regex", 10),
    ("Income", r"\b(nomina|n[oó]mina|salary|payroll|refund|devoluci[oó]n|ingreso\s*n[oó]mina)\b", "regex", 10),
]

EXPENSE_CATEGORY_NAMES = [name for name, kind, _ in DEFAULT_CATEGORIES if kind == "expense"]


def new_invite_code() -> str:
    return secrets.token_urlsafe(8)


def ensure_default_category_rules(db: Session, household_id: int) -> None:
    categories = {c.name: c for c in db.query(Category).filter(Category.household_id == household_id).all()}
    existing = {(r.category_id, r.pattern, r.match_type) for r in db.query(CategoryRule).join(Category).filter(Category.household_id == household_id).all()}
    for category_name, pattern, match_type, priority in DEFAULT_CATEGORY_RULES:
        category = categories.get(category_name)
        if category is None:
            continue
        if (category.id, pattern, match_type) in existing:
            continue
        db.add(CategoryRule(category_id=category.id, pattern=pattern, match_type=match_type, priority=priority))


def ensure_default_categories(db: Session, household_id: int) -> None:
    by_name = {c.name: c for c in db.query(Category).filter(Category.household_id == household_id).all()}
    for name, kind, color in DEFAULT_CATEGORIES:
        if name in by_name:
            continue
        db.add(Category(household_id=household_id, name=name, kind=kind, color=color, is_system=True))
    db.flush()
    ensure_default_category_rules(db, household_id)


def seed_household_defaults(db: Session, household: Household) -> None:
    for name, kind, color in DEFAULT_CATEGORIES:
        db.add(Category(household_id=household.id, name=name, kind=kind, color=color, is_system=True))
    db.flush()
    ensure_default_category_rules(db, household.id)


def ensure_all_household_defaults() -> None:
    db = SessionLocal()
    for household in db.query(Household).all():
        ensure_default_categories(db, household.id)
    db.commit()
    db.close()

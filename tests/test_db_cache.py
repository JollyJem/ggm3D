"""The Supabase read path: caching, and what a bad id does.

conftest forces local mode so real keys never leave the machine, so the
supabase branch is reached here with a stand-in client that counts queries.
"""

import pytest

from app import db
from app.seed_data import SEED_PRODUCTS

ROWS = [dict(p) for p in SEED_PRODUCTS]


class FakeQuery:
    def __init__(self, table: "FakeTable"):
        self.table = table
        self.filters: dict = {}

    def select(self, *_):
        return self

    def order(self, *_):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        if "id" in self.filters:
            wanted = self.filters["id"]
            if wanted not in {r["id"] for r in ROWS}:
                # what Postgres does with a value that is not a uuid at all
                raise ValueError(f'invalid input syntax for type uuid: "{wanted}"')
            return type("R", (), {"data": [r for r in ROWS if r["id"] == wanted]})
        return type("R", (), {"data": ROWS})


class FakeTable:
    def __init__(self, client):
        self.client = client

    def __getattr__(self, name):
        return getattr(FakeQuery(self), name)


class FakeClient:
    def __init__(self):
        self.queries = 0

    def table(self, _name):
        self.queries += 1
        return FakeQuery(FakeTable(self))


@pytest.fixture
def supabase(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(db, "get_client", lambda: client)
    db.invalidate_products()
    yield client
    db.invalidate_products()


def test_catalog_is_queried_once_across_repeated_views(supabase):
    for _ in range(5):
        assert len(db.list_products()) == len(ROWS)
    assert supabase.queries == 1, "the catalog should come from memory after the first read"


def test_detail_page_reuses_the_cached_catalog(supabase):
    db.list_products()
    before = supabase.queries
    for _ in range(10):  # a page load plus four polls
        assert db.get_product(ROWS[0]["id"]) is not None
    assert supabase.queries == before, "a known product must not cost a query"


def test_cache_lapses_after_the_ttl(supabase):
    db.list_products()
    assert supabase.queries == 1
    # Age the entry rather than patching the clock: time.monotonic counts from
    # boot, so pinning it to a literal is only "later" on a freshly started
    # machine and silently inverts the test once uptime passes that number.
    stamp, products = db._products_cache
    db._products_cache = (stamp - db.PRODUCT_TTL_SECONDS - 1, products)
    db.list_products()
    assert supabase.queries == 2


def test_unknown_id_is_absent_rather_than_an_error(supabase):
    """Postgres raises on a malformed uuid. A mistyped URL has to 404, not 500."""
    assert db.get_product("no-such-id") is None


def test_invalidate_forces_a_refetch(supabase):
    db.list_products()
    db.invalidate_products()
    db.list_products()
    assert supabase.queries == 2

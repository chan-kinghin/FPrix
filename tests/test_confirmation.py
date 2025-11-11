from __future__ import annotations

from app.services.confirmation import (
    needs_confirmation,
    generate_confirmation_id,
    save_confirmation,
    get_confirmation,
    pop_confirmation,
)


def test_needs_confirmation_rules():
    assert needs_confirmation(1, 1.0) is False
    assert needs_confirmation(1, 0.99) is True
    assert needs_confirmation(2, 1.0) is True
    assert needs_confirmation(0, 0.5) is False


def test_inmemory_confirmation_store_roundtrip():
    cid = generate_confirmation_id()
    opts = [{"id": "1", "product_code": "GT10S"}]
    params = {"tier": "C级", "color_type": "标准色"}
    save_confirmation(cid, opts, params, db=None)

    s = get_confirmation(cid, db=None)
    assert s is not None
    assert s.options and s.options[0]["product_code"] == "GT10S"
    assert s.params["tier"] == "C级"

    popped = pop_confirmation(cid, db=None)
    assert popped is not None
    assert get_confirmation(cid, db=None) is None


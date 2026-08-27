"""volfit.data.roots — the ONE index-root registry (parent ↔ weekly / PM
siblings) shared by the Cboe CDN symbol map, the snapshot-file alias search
and the snapshot export's ``root`` stamp."""

from volfit.data import cboe
from volfit.data.roots import (
    INDEX_ROOTS,
    PARENT_OF,
    aliases,
    is_index_root,
    normalize_root,
    parent_root,
    roots_of,
)


def test_parent_root_maps_siblings_and_is_identity_elsewhere():
    assert parent_root("SPXW") == "SPX" and parent_root("NDXP") == "NDX"
    assert parent_root("RUTW") == "RUT" and parent_root("XSPW") == "XSP" and parent_root("VIXW") == "VIX"
    assert parent_root("SPX") == "SPX"  # a parent is its own parent
    assert parent_root("SPY") == "SPY" and parent_root("nvda") == "NVDA"
    # Symbol spellings normalize first.
    assert parent_root("^spxw") == "SPX" and parent_root("_SPXW") == "SPX" and parent_root("SPXW Index") == "SPX"


def test_roots_of_lists_parent_first_then_siblings():
    assert roots_of("SPX") == ("SPX", "SPXW") and roots_of("SPXW") == ("SPX", "SPXW")
    assert roots_of("NDX") == ("NDX", "NDXP") and roots_of("VIX") == ("VIX", "VIXW")
    assert roots_of("RUT") == ("RUT", "RUTW") and roots_of("XSP") == ("XSP", "XSPW")
    assert roots_of("DJX") == ("DJX",)  # an index with no weekly root
    assert roots_of("SPY") == ("SPY",)


def test_aliases_start_with_the_ticker_itself():
    assert aliases("SPX") == ("SPX", "SPXW")
    assert aliases("SPXW") == ("SPXW", "SPX")
    assert aliases("XSPW") == ("XSPW", "XSP") and aliases("NDXP") == ("NDXP", "NDX")
    assert aliases("SPY") == ("SPY",) and aliases("nvda") == ("NVDA",)


def test_is_index_root_and_normalization():
    assert is_index_root("SPXW") and is_index_root("^SPX") and is_index_root("_VIX")
    assert is_index_root("SPX Index") and is_index_root("rut")
    assert not is_index_root("SPY") and not is_index_root("") and not is_index_root("NVDA")
    assert normalize_root("  ^spx ") == "SPX" and normalize_root("SPXW Index") == "SPXW"


def test_table_is_closed_and_shared_with_cboe():
    assert set(PARENT_OF) == set(INDEX_ROOTS)  # every index root has a parent entry
    assert set(PARENT_OF.values()) <= INDEX_ROOTS
    # ONE table: cboe consumes the registry objects, and cdn_symbol still maps
    # the weekly roots onto their parent file.
    assert cboe._PARENT_FILE is PARENT_OF and cboe.INDEX_ROOTS is INDEX_ROOTS
    assert cboe.cdn_symbol("SPXW") == "_SPX" and cboe.cdn_symbol("NDXP") == "_NDX"
    assert cboe.cdn_symbol("^RUTW") == "_RUT" and cboe.cdn_symbol("XSP") == "_XSP"
    assert cboe.cdn_symbol("SPY") == "SPY"

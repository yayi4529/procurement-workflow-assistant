from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.core.exceptions import AppError
from app.domain.equipment_specifications import (
    FORBIDDEN_RUNTIME_KEYS,
    RECOMMENDED_SPECIFICATION_KEYS,
)
from app.models.assets import (
    Asset,
    AssetComponent,
    AssetRelation,
    EquipmentCategory,
    EquipmentModel,
)
from app.services.assets import AssetQueryService
from scripts.seed_demo_data import (
    asset_rows,
    component_rows,
    equipment_category_rows,
    equipment_model_rows,
    relation_rows,
)


def test_seed_has_exact_five_domains_and_seventeen_types_with_shu_uninvented() -> None:
    rows = equipment_category_rows()
    domains = [row for row in rows if row["category_level"] == 1]
    types = [row for row in rows if row["category_level"] == 2]
    assert len(domains) == 5
    assert len(types) == 17
    assert len({row["category_code"] for row in rows}) == 22
    assert RECOMMENDED_SPECIFICATION_KEYS["SHU"] == frozenset()
    assert "current_alarm" in FORBIDDEN_RUNTIME_KEYS


def test_demo_seed_is_test_only_and_covers_models_assets_components_relations() -> None:
    assert {row["category_id"] for row in equipment_model_rows()} == {95014, 95016, 95017, 95026}
    assert all(str(row["asset_code"]).startswith("TEST-") for row in asset_rows())
    assert any(row["model_id"] is None for row in asset_rows())
    assert all(Decimal(row["quantity"]) > 0 for row in component_rows())
    assert {row["relation_type"] for row in relation_rows()} == {
        "CONNECTED_TO",
        "POWERED_BY",
        "COOLED_BY",
    }


def test_five_models_expose_required_database_constraints() -> None:
    assert EquipmentCategory.__tablename__ == "equipment_category"
    assert EquipmentModel.__tablename__ == "equipment_model"
    assert Asset.__tablename__ == "asset"
    assert AssetComponent.__tablename__ == "asset_component"
    assert AssetRelation.__tablename__ == "asset_relation"
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_asset_code"
        for item in Asset.__table__.constraints
    )
    assert any(
        isinstance(item, CheckConstraint) and "quantity > 0" in str(item.sqltext)
        for item in AssetComponent.__table__.constraints
    )
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_asset_relation"
        for item in AssetRelation.__table__.constraints
    )


def test_service_rejects_category_mismatch_self_relation_and_unknown_relation() -> None:
    model = EquipmentModel(category_id=2, model="TEST", lifecycle_status="ACTIVE")
    with pytest.raises(AppError) as mismatch:
        AssetQueryService.validate_asset_model_category(asset_category_id=1, model=model)
    assert mismatch.value.code == "ASSET_MODEL_CATEGORY_MISMATCH"
    with pytest.raises(AppError) as self_relation:
        AssetQueryService.validate_relation(
            source_asset_id=1, target_asset_id=1, relation_type="CONNECTED_TO"
        )
    assert self_relation.value.code == "ASSET_RELATION_SELF_REFERENCE"
    with pytest.raises(AppError):
        AssetQueryService.validate_relation(
            source_asset_id=1, target_asset_id=2, relation_type="INVENTED"
        )

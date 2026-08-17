from procurement_platform.adapters.backend.dto import (
    BackendCreatedRequirementDTO,
    BackendCurrentUserDTO,
    BackendHandlerCandidatesDTO,
)
from procurement_platform.adapters.backend.mapper import (
    map_created_requirement,
    map_current_user,
    map_handler_candidates,
)
from procurement_platform.domain.enums import PlatformType, RoleCode


def test_map_current_user_keeps_only_domain_fields() -> None:
    dto = BackendCurrentUserDTO.model_validate(
        {
            "employee_id": 7,
            "employee_no": "TEST-E007",
            "name": "测试需求人",
            "mobile": None,
            "status": "ACTIVE",
            "platform_type": "FEISHU",
            "platform_user_id": "ou_test",
            "roles": [
                {
                    "role_id": 1,
                    "role_code": "APPLICANT",
                    "role_name": "需求人",
                }
            ],
            "buildings": [
                {
                    "building_id": 1,
                    "building_name": "一号楼",
                    "is_primary": True,
                }
            ],
        }
    )

    user = map_current_user(dto)

    assert dto.platform_type is PlatformType.FEISHU
    assert user.employee_id == 7
    assert user.roles[0].role_code is RoleCode.APPLICANT
    assert user.buildings[0].building_id == 1
    assert "employee_no" not in type(user).model_fields
    assert "platform_user_id" not in type(user).model_fields


def test_map_created_requirement_drops_transport_only_fields() -> None:
    dto = BackendCreatedRequirementDTO.model_validate(
        {
            "requirement_id": 10,
            "requirement_no": "PR-10",
            "status": "DRAFT",
            "version": 1,
            "current_handler": {
                "employee_id": 7,
                "name": "测试需求人",
                "platform_identities": [
                    {
                        "platform_type": "FEISHU",
                        "platform_user_id": "ou_test",
                    }
                ],
            },
            "completed_at": None,
        }
    )

    summary = map_created_requirement(dto)

    assert summary.requirement_id == 10
    assert summary.requirement_no == "PR-10"
    assert "current_handler" not in type(summary).model_fields
    assert "completed_at" not in type(summary).model_fields


def test_map_handler_candidates_drops_masked_mobile() -> None:
    dto = BackendHandlerCandidatesDTO.model_validate(
        {
            "items": [
                {
                    "employee_id": 9,
                    "name": "测试楼长",
                    "mobile": "138****9002",
                }
            ],
            "auto_selected_employee_id": 9,
        }
    )

    candidates = map_handler_candidates(dto)

    assert candidates.items[0].employee_id == 9
    assert candidates.items[0].name == "测试楼长"
    assert "mobile" not in type(candidates.items[0]).model_fields

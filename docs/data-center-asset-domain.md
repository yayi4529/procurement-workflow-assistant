# Data Center Asset Domain (Task05)

Task05 adds a lightweight, read-oriented equipment and asset domain without changing the existing procurement workflow.

## Data model

Exactly five core tables are added:

```text
equipment_category -> equipment_model -> asset -> asset_component
                                           \-> asset_relation -> asset
```

- `equipment_category` stores a tree with five level-1 domains and seventeen level-2 equipment types.
- `equipment_model` stores shared manufacturer/model specifications.
- `asset` stores one installed site asset and may have an unknown (`NULL`) model.
- `asset_component` stores coarse, maintainable major components, not a complete BOM.
- `asset_relation` stores `CONNECTED_TO`, `POWERED_BY`, `FEEDS`, `COOLED_BY`, `MONITORED_BY`, and `DEPENDS_ON` facts.

The five domains are `POWER`, `COOLING`, `MONITORING_ENV`, `ICT`, and `OM`. SHU remains the internal code/name `SHU`; no unconfirmed expansion or dedicated specification schema is invented.

## Model, asset, and JSON boundaries

`equipment_model.specifications` contains stable facts shared by a model. `asset.configuration` contains stable instance configuration. Neither field stores current load, temperature, alarms, fault state, maintenance history, or other high-frequency telemetry. `asset.aliases` is a small JSON list used for deterministic entity resolution.

## Query and authorization boundary

All asset facts remain in Backend MySQL. The root Agent calls the signed `BackendClient` HTTP port and never imports Backend ORM or connects to MySQL/Redis. ADMIN can query all buildings; other users are restricted to Backend-provided building memberships. Redis may retain short-lived references or candidates but is not authoritative.

`GET /api/v1/assets/{asset_id}/context` aggregates the asset, category, optional model, components, relations, and redundancy peers. Agent component and relation capabilities each use one context request rather than a serial HTTP N+1 chain.

## Agent behavior

Stable references are `asset:{asset_id}` and `model:{model_id}`. Resolution ranks exact asset code, exact name, exact normalized alias, then candidate search. Multiple candidates are returned as ambiguous and are never silently guessed. Missing model, component, or relation data is reported as missing and is never filled from model knowledge.

All Task05 capabilities are read-only: `search_assets`, `resolve_asset`, `get_asset`, `get_asset_components`, and `get_asset_relations`.

## Deferred scope

- Task06: purchase request items and `source_asset_id` linkage.
- Task07: fault reasoning, alarm diagnosis, and repair guidance.
- Task08: inventory, spare parts, compatibility, and BOM packages.

The existing deterministic card workflow, states, versions, action tokens, supplier blacklist, warehouse receipt, and notification outbox are unchanged.

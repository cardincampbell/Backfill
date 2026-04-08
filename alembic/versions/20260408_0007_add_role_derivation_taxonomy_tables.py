"""add business role derivation taxonomy tables

Revision ID: 20260408_0007
Revises: 20260407_0006
Create Date: 2026-04-08 15:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260408_0007"
down_revision = "20260407_0006"
branch_labels = None
depends_on = None


def _vertical_rows() -> list[dict[str, object]]:
    return [
        {"code": "restaurant", "display_name": "Restaurant"},
        {"code": "cafe", "display_name": "Cafe"},
        {"code": "bakery", "display_name": "Bakery"},
        {"code": "bar", "display_name": "Bar"},
        {"code": "retail", "display_name": "Retail"},
        {"code": "beauty", "display_name": "Beauty"},
        {"code": "fitness", "display_name": "Fitness"},
        {"code": "medical_clinic", "display_name": "Medical Clinic"},
        {"code": "dental_clinic", "display_name": "Dental Clinic"},
        {"code": "home_services", "display_name": "Home Services"},
        {"code": "warehouse", "display_name": "Warehouse"},
        {"code": "hotel", "display_name": "Hotel"},
        {"code": "professional_office", "display_name": "Professional Office"},
        {"code": "mixed_unknown", "display_name": "Mixed / Unknown"},
    ]


def _vertical_type_mapping_rows() -> list[dict[str, object]]:
    return [
        {"place_type": "restaurant", "business_vertical_code": "restaurant", "subvertical_code": "full_service_restaurant"},
        {"place_type": "meal_takeaway", "business_vertical_code": "restaurant", "subvertical_code": "takeout_restaurant"},
        {"place_type": "meal_delivery", "business_vertical_code": "restaurant", "subvertical_code": "delivery_restaurant"},
        {"place_type": "cafe", "business_vertical_code": "cafe", "subvertical_code": "cafe"},
        {"place_type": "coffee_shop", "business_vertical_code": "cafe", "subvertical_code": "coffee_shop"},
        {"place_type": "bakery", "business_vertical_code": "bakery", "subvertical_code": "bakery"},
        {"place_type": "bar", "business_vertical_code": "bar", "subvertical_code": "bar"},
        {"place_type": "pub", "business_vertical_code": "bar", "subvertical_code": "pub"},
        {"place_type": "wine_bar", "business_vertical_code": "bar", "subvertical_code": "wine_bar"},
        {"place_type": "night_club", "business_vertical_code": "bar", "subvertical_code": "nightlife"},
        {"place_type": "grocery_store", "business_vertical_code": "retail", "subvertical_code": "grocery"},
        {"place_type": "supermarket", "business_vertical_code": "retail", "subvertical_code": "grocery"},
        {"place_type": "convenience_store", "business_vertical_code": "retail", "subvertical_code": "convenience"},
        {"place_type": "store", "business_vertical_code": "retail", "subvertical_code": None},
        {"place_type": "department_store", "business_vertical_code": "retail", "subvertical_code": "department_store"},
        {"place_type": "shopping_mall", "business_vertical_code": "retail", "subvertical_code": "shopping_center"},
        {"place_type": "clothing_store", "business_vertical_code": "retail", "subvertical_code": "apparel"},
        {"place_type": "shoe_store", "business_vertical_code": "retail", "subvertical_code": "apparel"},
        {"place_type": "book_store", "business_vertical_code": "retail", "subvertical_code": "specialty_retail"},
        {"place_type": "hair_salon", "business_vertical_code": "beauty", "subvertical_code": "hair_salon"},
        {"place_type": "beauty_salon", "business_vertical_code": "beauty", "subvertical_code": "beauty_salon"},
        {"place_type": "barber_shop", "business_vertical_code": "beauty", "subvertical_code": "barber_shop"},
        {"place_type": "nail_salon", "business_vertical_code": "beauty", "subvertical_code": "nail_salon"},
        {"place_type": "spa", "business_vertical_code": "beauty", "subvertical_code": "spa"},
        {"place_type": "gym", "business_vertical_code": "fitness", "subvertical_code": "gym"},
        {"place_type": "fitness_center", "business_vertical_code": "fitness", "subvertical_code": "fitness_center"},
        {"place_type": "yoga_studio", "business_vertical_code": "fitness", "subvertical_code": "yoga_studio"},
        {"place_type": "pilates_studio", "business_vertical_code": "fitness", "subvertical_code": "pilates_studio"},
        {"place_type": "dentist", "business_vertical_code": "dental_clinic", "subvertical_code": "dentistry"},
        {"place_type": "orthodontist", "business_vertical_code": "dental_clinic", "subvertical_code": "orthodontics"},
        {"place_type": "doctor", "business_vertical_code": "medical_clinic", "subvertical_code": "doctor_office"},
        {"place_type": "hospital", "business_vertical_code": "medical_clinic", "subvertical_code": "hospital"},
        {"place_type": "medical_lab", "business_vertical_code": "medical_clinic", "subvertical_code": "medical_lab"},
        {"place_type": "urgent_care_center", "business_vertical_code": "medical_clinic", "subvertical_code": "urgent_care"},
        {"place_type": "pharmacy", "business_vertical_code": "medical_clinic", "subvertical_code": "pharmacy"},
        {"place_type": "electrician", "business_vertical_code": "home_services", "subvertical_code": "electrical"},
        {"place_type": "plumber", "business_vertical_code": "home_services", "subvertical_code": "plumbing"},
        {"place_type": "roofing_contractor", "business_vertical_code": "home_services", "subvertical_code": "roofing"},
        {"place_type": "hvac_contractor", "business_vertical_code": "home_services", "subvertical_code": "hvac"},
        {"place_type": "general_contractor", "business_vertical_code": "home_services", "subvertical_code": "contracting"},
        {"place_type": "locksmith", "business_vertical_code": "home_services", "subvertical_code": "locksmith"},
        {"place_type": "moving_company", "business_vertical_code": "home_services", "subvertical_code": "moving"},
        {"place_type": "painter", "business_vertical_code": "home_services", "subvertical_code": "painting"},
        {"place_type": "warehouse", "business_vertical_code": "warehouse", "subvertical_code": "warehouse"},
        {"place_type": "storage", "business_vertical_code": "warehouse", "subvertical_code": "storage"},
        {"place_type": "self_storage", "business_vertical_code": "warehouse", "subvertical_code": "storage"},
        {"place_type": "lodging", "business_vertical_code": "hotel", "subvertical_code": "lodging"},
        {"place_type": "hotel", "business_vertical_code": "hotel", "subvertical_code": "hotel"},
        {"place_type": "motel", "business_vertical_code": "hotel", "subvertical_code": "motel"},
        {"place_type": "resort_hotel", "business_vertical_code": "hotel", "subvertical_code": "resort"},
        {"place_type": "lawyer", "business_vertical_code": "professional_office", "subvertical_code": "legal"},
        {"place_type": "accounting", "business_vertical_code": "professional_office", "subvertical_code": "accounting"},
        {"place_type": "insurance_agency", "business_vertical_code": "professional_office", "subvertical_code": "insurance"},
        {"place_type": "real_estate_agency", "business_vertical_code": "professional_office", "subvertical_code": "real_estate"},
        {"place_type": "bank", "business_vertical_code": "professional_office", "subvertical_code": "finance"},
        {"place_type": "corporate_office", "business_vertical_code": "professional_office", "subvertical_code": "office"},
    ]


def _business_role_archetype_rows() -> list[dict[str, object]]:
    return [
        {"code": "general_manager", "display_name": "General Manager", "role_family": "management"},
        {"code": "assistant_manager", "display_name": "Assistant Manager", "role_family": "management"},
        {"code": "shift_lead", "display_name": "Shift Lead", "role_family": "operations"},
        {"code": "server", "display_name": "Server", "role_family": "front_of_house"},
        {"code": "host", "display_name": "Host", "role_family": "front_of_house"},
        {"code": "line_cook", "display_name": "Line Cook", "role_family": "back_of_house"},
        {"code": "dishwasher", "display_name": "Dishwasher", "role_family": "back_of_house"},
        {"code": "bartender", "display_name": "Bartender", "role_family": "front_of_house"},
        {"code": "barback", "display_name": "Barback", "role_family": "front_of_house"},
        {"code": "barista", "display_name": "Barista", "role_family": "front_of_house"},
        {"code": "cashier", "display_name": "Cashier", "role_family": "front_of_house"},
        {"code": "prep_kitchen", "display_name": "Prep Kitchen", "role_family": "back_of_house"},
        {"code": "baker", "display_name": "Baker", "role_family": "back_of_house"},
        {"code": "store_manager", "display_name": "Store Manager", "role_family": "management"},
        {"code": "sales_associate", "display_name": "Sales Associate", "role_family": "sales"},
        {"code": "stock_associate", "display_name": "Stock Associate", "role_family": "inventory"},
        {"code": "pickup_associate", "display_name": "Pickup Associate", "role_family": "front_of_house"},
        {"code": "inventory_lead", "display_name": "Inventory Lead", "role_family": "inventory"},
        {"code": "location_manager", "display_name": "Location Manager", "role_family": "management"},
        {"code": "receptionist", "display_name": "Receptionist", "role_family": "front_desk"},
        {"code": "stylist", "display_name": "Stylist", "role_family": "service"},
        {"code": "assistant", "display_name": "Assistant", "role_family": "service"},
        {"code": "esthetician", "display_name": "Esthetician", "role_family": "service"},
        {"code": "nail_technician", "display_name": "Nail Technician", "role_family": "service"},
        {"code": "coach_trainer", "display_name": "Coach / Trainer", "role_family": "service"},
        {"code": "front_desk_associate", "display_name": "Front Desk Associate", "role_family": "front_desk"},
        {"code": "practice_manager", "display_name": "Practice Manager", "role_family": "management"},
        {"code": "medical_assistant", "display_name": "Medical Assistant", "role_family": "clinical"},
        {"code": "dental_assistant", "display_name": "Dental Assistant", "role_family": "clinical"},
        {"code": "dental_hygienist", "display_name": "Dental Hygienist", "role_family": "clinical"},
        {"code": "operations_manager", "display_name": "Operations Manager", "role_family": "management"},
        {"code": "dispatcher", "display_name": "Dispatcher", "role_family": "operations"},
        {"code": "field_technician", "display_name": "Field Technician", "role_family": "field"},
        {"code": "installer", "display_name": "Installer", "role_family": "field"},
        {"code": "estimator", "display_name": "Estimator", "role_family": "operations"},
        {"code": "customer_support", "display_name": "Customer Support", "role_family": "support"},
        {"code": "site_manager", "display_name": "Site Manager", "role_family": "management"},
        {"code": "shift_supervisor", "display_name": "Shift Supervisor", "role_family": "operations"},
        {"code": "picker_packer", "display_name": "Picker / Packer", "role_family": "warehouse"},
        {"code": "inventory_associate", "display_name": "Inventory Associate", "role_family": "warehouse"},
        {"code": "receiving_clerk", "display_name": "Receiving Clerk", "role_family": "warehouse"},
        {"code": "forklift_operator", "display_name": "Forklift Operator", "role_family": "warehouse"},
        {"code": "housekeeper", "display_name": "Housekeeper", "role_family": "operations"},
        {"code": "maintenance_technician", "display_name": "Maintenance Technician", "role_family": "operations"},
        {"code": "night_auditor", "display_name": "Night Auditor", "role_family": "operations"},
        {"code": "office_manager", "display_name": "Office Manager", "role_family": "management"},
        {"code": "coordinator", "display_name": "Coordinator", "role_family": "operations"},
        {"code": "delivery_coordinator", "display_name": "Delivery Coordinator", "role_family": "operations"},
        {"code": "expeditor", "display_name": "Expeditor", "role_family": "operations"},
        {"code": "food_runner", "display_name": "Food Runner", "role_family": "front_of_house"},
        {"code": "expo", "display_name": "Expo", "role_family": "back_of_house"},
    ]


def _business_vertical_role_archetype_rows() -> list[dict[str, object]]:
    return [
        {"business_vertical_code": "restaurant", "business_role_code": "general_manager", "sort_order": 10},
        {"business_vertical_code": "restaurant", "business_role_code": "assistant_manager", "sort_order": 20},
        {"business_vertical_code": "restaurant", "business_role_code": "shift_lead", "sort_order": 30},
        {"business_vertical_code": "restaurant", "business_role_code": "server", "sort_order": 40},
        {"business_vertical_code": "restaurant", "business_role_code": "host", "sort_order": 50},
        {"business_vertical_code": "restaurant", "business_role_code": "line_cook", "sort_order": 60},
        {"business_vertical_code": "restaurant", "business_role_code": "dishwasher", "sort_order": 70},
        {"business_vertical_code": "cafe", "business_role_code": "general_manager", "sort_order": 10},
        {"business_vertical_code": "cafe", "business_role_code": "shift_lead", "sort_order": 20},
        {"business_vertical_code": "cafe", "business_role_code": "barista", "sort_order": 30},
        {"business_vertical_code": "cafe", "business_role_code": "cashier", "sort_order": 40},
        {"business_vertical_code": "cafe", "business_role_code": "prep_kitchen", "sort_order": 50},
        {"business_vertical_code": "bakery", "business_role_code": "general_manager", "sort_order": 10},
        {"business_vertical_code": "bakery", "business_role_code": "shift_lead", "sort_order": 20},
        {"business_vertical_code": "bakery", "business_role_code": "baker", "sort_order": 30},
        {"business_vertical_code": "bakery", "business_role_code": "cashier", "sort_order": 40},
        {"business_vertical_code": "bakery", "business_role_code": "prep_kitchen", "sort_order": 50},
        {"business_vertical_code": "bar", "business_role_code": "general_manager", "sort_order": 10},
        {"business_vertical_code": "bar", "business_role_code": "assistant_manager", "sort_order": 20},
        {"business_vertical_code": "bar", "business_role_code": "shift_lead", "sort_order": 30},
        {"business_vertical_code": "bar", "business_role_code": "bartender", "sort_order": 40},
        {"business_vertical_code": "bar", "business_role_code": "barback", "sort_order": 50},
        {"business_vertical_code": "bar", "business_role_code": "host", "sort_order": 60},
        {"business_vertical_code": "retail", "business_role_code": "store_manager", "sort_order": 10},
        {"business_vertical_code": "retail", "business_role_code": "assistant_manager", "sort_order": 20},
        {"business_vertical_code": "retail", "business_role_code": "shift_lead", "sort_order": 30},
        {"business_vertical_code": "retail", "business_role_code": "sales_associate", "sort_order": 40},
        {"business_vertical_code": "retail", "business_role_code": "cashier", "sort_order": 50},
        {"business_vertical_code": "retail", "business_role_code": "stock_associate", "sort_order": 60},
        {"business_vertical_code": "beauty", "business_role_code": "location_manager", "sort_order": 10},
        {"business_vertical_code": "beauty", "business_role_code": "receptionist", "sort_order": 20},
        {"business_vertical_code": "beauty", "business_role_code": "stylist", "sort_order": 30},
        {"business_vertical_code": "beauty", "business_role_code": "assistant", "sort_order": 40},
        {"business_vertical_code": "fitness", "business_role_code": "general_manager", "sort_order": 10},
        {"business_vertical_code": "fitness", "business_role_code": "shift_lead", "sort_order": 20},
        {"business_vertical_code": "fitness", "business_role_code": "front_desk_associate", "sort_order": 30},
        {"business_vertical_code": "fitness", "business_role_code": "coach_trainer", "sort_order": 40},
        {"business_vertical_code": "medical_clinic", "business_role_code": "practice_manager", "sort_order": 10},
        {"business_vertical_code": "medical_clinic", "business_role_code": "receptionist", "sort_order": 20},
        {"business_vertical_code": "medical_clinic", "business_role_code": "medical_assistant", "sort_order": 30},
        {"business_vertical_code": "dental_clinic", "business_role_code": "practice_manager", "sort_order": 10},
        {"business_vertical_code": "dental_clinic", "business_role_code": "receptionist", "sort_order": 20},
        {"business_vertical_code": "dental_clinic", "business_role_code": "dental_assistant", "sort_order": 30},
        {"business_vertical_code": "dental_clinic", "business_role_code": "dental_hygienist", "sort_order": 40},
        {"business_vertical_code": "home_services", "business_role_code": "operations_manager", "sort_order": 10},
        {"business_vertical_code": "home_services", "business_role_code": "dispatcher", "sort_order": 20},
        {"business_vertical_code": "home_services", "business_role_code": "field_technician", "sort_order": 30},
        {"business_vertical_code": "home_services", "business_role_code": "estimator", "sort_order": 40},
        {"business_vertical_code": "home_services", "business_role_code": "customer_support", "sort_order": 50},
        {"business_vertical_code": "warehouse", "business_role_code": "site_manager", "sort_order": 10},
        {"business_vertical_code": "warehouse", "business_role_code": "shift_supervisor", "sort_order": 20},
        {"business_vertical_code": "warehouse", "business_role_code": "picker_packer", "sort_order": 30},
        {"business_vertical_code": "warehouse", "business_role_code": "inventory_associate", "sort_order": 40},
        {"business_vertical_code": "warehouse", "business_role_code": "receiving_clerk", "sort_order": 50},
        {"business_vertical_code": "hotel", "business_role_code": "general_manager", "sort_order": 10},
        {"business_vertical_code": "hotel", "business_role_code": "front_desk_associate", "sort_order": 20},
        {"business_vertical_code": "hotel", "business_role_code": "housekeeper", "sort_order": 30},
        {"business_vertical_code": "hotel", "business_role_code": "maintenance_technician", "sort_order": 40},
        {"business_vertical_code": "hotel", "business_role_code": "night_auditor", "sort_order": 50},
        {"business_vertical_code": "professional_office", "business_role_code": "office_manager", "sort_order": 10},
        {"business_vertical_code": "professional_office", "business_role_code": "receptionist", "sort_order": 20},
        {"business_vertical_code": "professional_office", "business_role_code": "coordinator", "sort_order": 30},
        {"business_vertical_code": "mixed_unknown", "business_role_code": "general_manager", "sort_order": 10},
    ]


def upgrade() -> None:
    op.create_table(
        "business_verticals",
        sa.Column("code", sa.String(length=80), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "business_vertical_type_mappings",
        sa.Column("place_type", sa.String(length=120), primary_key=True),
        sa.Column("business_vertical_code", sa.String(length=80), sa.ForeignKey("business_verticals.code", ondelete="CASCADE"), nullable=False),
        sa.Column("subvertical_code", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_business_vertical_type_mappings_business_vertical_code_is_active",
        "business_vertical_type_mappings",
        ["business_vertical_code", "is_active"],
    )
    op.create_table(
        "business_place_types",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_provider", sa.String(length=80), nullable=False, server_default="google_places"),
        sa.Column("place_type", sa.String(length=120), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_business_place_types_business_id_location_id",
        "business_place_types",
        ["business_id", "location_id"],
    )
    op.create_index(
        "ix_business_place_types_business_id_source_provider",
        "business_place_types",
        ["business_id", "source_provider"],
    )
    op.create_table(
        "business_role_archetypes",
        sa.Column("code", sa.String(length=80), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role_family", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "business_vertical_role_archetypes",
        sa.Column("business_vertical_code", sa.String(length=80), sa.ForeignKey("business_verticals.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("business_role_code", sa.String(length=80), sa.ForeignKey("business_role_archetypes.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_business_vertical_role_archetypes_vertical_code_is_active",
        "business_vertical_role_archetypes",
        ["business_vertical_code", "is_active"],
    )

    business_verticals = sa.table(
        "business_verticals",
        sa.column("code", sa.String()),
        sa.column("display_name", sa.String()),
    )
    business_vertical_type_mappings = sa.table(
        "business_vertical_type_mappings",
        sa.column("place_type", sa.String()),
        sa.column("business_vertical_code", sa.String()),
        sa.column("subvertical_code", sa.String()),
    )
    business_role_archetypes = sa.table(
        "business_role_archetypes",
        sa.column("code", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("role_family", sa.String()),
    )
    business_vertical_role_archetypes = sa.table(
        "business_vertical_role_archetypes",
        sa.column("business_vertical_code", sa.String()),
        sa.column("business_role_code", sa.String()),
        sa.column("sort_order", sa.Integer()),
    )

    op.bulk_insert(business_verticals, _vertical_rows())
    op.bulk_insert(business_vertical_type_mappings, _vertical_type_mapping_rows())
    op.bulk_insert(business_role_archetypes, _business_role_archetype_rows())
    op.bulk_insert(
        business_vertical_role_archetypes,
        _business_vertical_role_archetype_rows(),
    )

def downgrade() -> None:
    op.drop_index(
        "ix_business_vertical_role_archetypes_vertical_code_is_active",
        table_name="business_vertical_role_archetypes",
    )
    op.drop_table("business_vertical_role_archetypes")
    op.drop_table("business_role_archetypes")
    op.drop_index(
        "ix_business_place_types_business_id_source_provider",
        table_name="business_place_types",
    )
    op.drop_index(
        "ix_business_place_types_business_id_location_id",
        table_name="business_place_types",
    )
    op.drop_table("business_place_types")
    op.drop_index(
        "ix_business_vertical_type_mappings_business_vertical_code_is_active",
        table_name="business_vertical_type_mappings",
    )
    op.drop_table("business_vertical_type_mappings")
    op.drop_table("business_verticals")

"""Port de supabase/functions/_shared/checklist-registry.ts.

Fonte da verdade do mapeamento parte do checklist -> tabela do banco e da
whitelist de colunas graváveis (impede injeção de colunas arbitrárias no upsert).
"""
from dataclasses import dataclass, field


@dataclass
class ChecklistPart:
    key: str
    label: str
    table: str
    fk_column: str
    instance_column: str | None = None
    append_only: bool = False
    columns: list[str] = field(default_factory=list)


CHECKLIST_REGISTRY: list[ChecklistPart] = [
    ChecklistPart(
        key="power_supply_input",
        label="Entrada de Alimentação",
        table="power_supply_input",
        fk_column="service_order_id",
        columns=[
            "installation_type", "photo_substation_front_url", "photo_substation_side_url",
            "photo_connection_branch_url", "photo_meter_url", "photo_polymer_detail_url",
            "photo_dte_url", "observations", "pole_status", "crossarms_status",
            "hardware_status", "loops_status", "insulators_status", "terminations_status",
            "connections_status", "lightning_arresters_status", "meter_display_status",
            "disconnect_switch_status", "conduit_status", "grounding_status",
        ],
    ),
    ChecklistPart(
        key="general_conditions",
        label="Condições Gerais",
        table="general_conditions",
        fk_column="service_order_id",
        columns=[
            "photo_environment_url", "photo_extinguisher_url", "photo_safety_gear_url",
            "photo_diagram_url", "photo_access_gates_url", "walls_ceiling_floor_status",
            "emergency_lighting_status", "extinguisher_co2_status", "extinguisher_last_recharge",
            "rubber_gloves_hv_status", "gloves_box_status", "ambient_temperature",
            "rubber_mat_status", "single_line_diagram_status", "warning_signs_status",
            "are_gates_doors_grounded", "are_gates_doors_locked", "gates_doors_condition",
            "relative_humidity",
        ],
    ),
    ChecklistPart(
        key="transformer_inspection",
        label="Inspeção de Transformador",
        table="transformer_inspection",
        fk_column="service_order_id",
        instance_column="transformer_number",
        columns=[
            "photo_plate_url", "photo_bushings_url", "photo_secondary_conductors_url",
            "photo_grounding_url", "photo_oil_level_or_tap_url", "photo_dte_url",
            "observations", "power_rating", "manufacturer", "serial_number",
            "manufacturing_date", "total_mass", "secondary_voltage", "oil_volume",
            "current_tap", "primary_gaskets_status", "secondary_gaskets_status",
            "oil_level_status", "has_oxidation_marks", "has_visible_oil_leak",
            "is_grounded_carcass_x0",
        ],
    ),
    ChecklistPart(
        key="general_protection_panel",
        label="Painel de Proteção Geral",
        table="general_protection_panel",
        fk_column="service_order_id",
        instance_column="panel_number",
        columns=[
            "photo_panel_closed_url", "photo_panel_open_url", "photo_details_url",
            "main_breaker_capacity", "main_breaker_adjustment", "conductor_section_phase",
            "conductor_section_neutral", "grounding_resistance_ohms", "insulation_type",
            "has_oxidation_marks", "is_panel_grounded", "voltage_r_s", "voltage_s_t",
            "voltage_r_t", "voltage_r_n", "voltage_s_n", "voltage_t_n",
            "current_r", "current_s", "current_t",
        ],
    ),
    ChecklistPart(
        key="low_voltage_main_panel",
        label="Quadro Geral de Baixa Tensão (QGBT)",
        table="low_voltage_main_panel",
        fk_column="service_order_id",
        instance_column="panel_number",
        columns=[
            "photo_panel_closed_url", "photo_panel_open_url", "photo_main_breaker_url",
            "photo_dps_dr_url", "photo_grounding_url", "photo_environment_url",
            "photo_dte_url", "observations", "physical_protection_type",
            "has_oxidation_marks", "is_panel_grounded", "voltage_r_s", "voltage_s_t",
            "voltage_r_t", "voltage_r_n", "voltage_s_n", "voltage_t_n",
            "current_r", "current_s", "current_t",
        ],
    ),
    ChecklistPart(
        key="medium_voltage_protection",
        label="Proteção de Média Tensão",
        table="medium_voltage_protection",
        fk_column="service_order",  # exceção: FK sem o sufixo _id
        columns=[
            "photo_disconnect_switch_url", "photo_cb_front_url", "photo_cb_back_url",
            "photo_relay_url", "photo_transformers_url", "photo_ups_url", "photo_dte_url",
            "observations", "disconnect_switch_manufacturer", "disconnect_switch_rated_current",
            "has_arc_suppressors", "has_hh_fuses", "hh_fuse_current", "circuit_breaker_type",
            "circuit_breaker_manufacturer", "circuit_breaker_serial_number",
            "circuit_breaker_rated_voltage_ur", "circuit_breaker_nbi_val", "relay_manufacturer",
            "relay_model", "relay_serial_number", "relay_rtc", "relay_rtp",
            "ups_input_voltage", "ups_output_voltage", "ups_status_normal",
        ],
    ),
    ChecklistPart(
        key="capacitor_bank",
        label="Banco de Capacitores",
        table="capacitor_bank",
        fk_column="service_order_id",
        columns=[
            "photo_panel_closed_url", "photo_panel_open_url", "photo_main_breaker_url",
            "photo_dps_dr_url", "photo_grounding_url", "photo_environment_url", "photo_dte_url",
            "activation_device_type", "model", "manufacturer", "outputs_count",
            "general_protection_r", "general_protection_s", "general_protection_t",
            "feeder_section_r", "feeder_section_s", "feeder_section_t",
            "heating_marks_status", "cells_measurements_data",
        ],
    ),
    ChecklistPart(
        key="general_observations",
        label="Observações Gerais",
        table="general_observations",
        fk_column="service_order_id",
        columns=[
            "oil_collection_status", "oil_collection_reason", "general_notes",
            "materials_needed_list", "photo_oil_collection_url", "photo_pending_maintenance_url",
        ],
    ),
    ChecklistPart(
        key="additional_services_executed",
        label="Serviços Adicionais Executados",
        table="additional_services_executed",
        fk_column="service_order_id",
        append_only=True,
        columns=["description", "photo_before_url", "photo_after_url"],
    ),
]

CHECKLIST_PART_ORDER = [p.key for p in CHECKLIST_REGISTRY]

_BY_KEY = {p.key: p for p in CHECKLIST_REGISTRY}


def get_part(key: str) -> ChecklistPart | None:
    return _BY_KEY.get(key)

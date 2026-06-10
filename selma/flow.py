"""Definição declarativa do fluxo de inspeção, replicando estritamente os bots
Typebot de `automacao/*.json`.

Ordem dos bots (confirmada pelos `Typebot link`):
  entrada-alimentacao -> protecao-media-tensao -> transformador ->
  quadro-protecao-geral -> quadro-geral-baixa-tensao -> banco-capacitores ->
  condicoes-gerais -> servicos-executados -> observacoes-gerais

Cada etapa expõe `build_script(vals)` que devolve a lista ORDENADA de perguntas
ainda aplicáveis dado o estado atual das respostas (`vals`: var -> valor). As
ramificações/pulos do Typebot são reproduzidas por meio de condicionais aqui.

O motor (`next_question`) percorre o script e devolve a primeira pergunta cujo
`qkey` ainda não foi respondido. Perguntas de "Descreva a situação" usam um
`qkey` próprio (var + "_desc") mas gravam na MESMA variável — como são inseridas
depois da escolha, sobrescrevem o valor "OBS"/"Não" ao derivar os valores finais.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Question:
    qkey: str
    var: str
    text: str
    qtype: str  # 'text' | 'choice'
    options: list[str] | None = None
    section: str | None = None  # cabeçalho/instrução exibido antes da pergunta


def T(var: str, text: str, section: str | None = None, qkey: str | None = None) -> Question:
    return Question(qkey or var, var, text, "text", None, section)


def C(var: str, text: str, options: list[str], section: str | None = None) -> Question:
    return Question(var, var, text, "choice", options, section)


def DESC(var: str, text: str = "Descreva a Situação") -> Question:
    return Question(f"{var}_desc", var, text, "text", None, None)


# --------------------------------------------------------------------------
# Scripts por etapa
# --------------------------------------------------------------------------

def s_power_supply(vals: dict) -> list[Question]:
    return [
        C("installation_type", "Qual é o tipo de Medição do local?",
          ["Conjunto Polimérico", "Shopping", "Cubículo/Cabine"]),
        T("pole_status", "Poste"),
        T("crossarms_status", "Cruzetas"),
        T("hardware_status", "Ferragens"),
        T("loops_status", "Alças"),
        T("insulators_status", "Isoladores"),
        T("terminations_status", "Muflas"),
        T("connections_status", "Conexões"),
        T("lightning_arresters_status", "Para-raios"),
        T("meter_display_status", "Display da medição"),
        T("disconnect_switch_status", "Chave seccionadora"),
        T("conduit_status", "Eletroduto"),
        T("grounding_status", "Tem aterramento?"),
    ]


def s_medium_voltage(vals: dict) -> list[Question]:
    qs = [
        T("disconnect_switch_manufacturer", "Fabricante", section="1. Chave Seccionadora:"),
        T("disconnect_switch_rated_current", "Corrente nominal"),
        C("has_arc_suppressors", "Possui supressor de arco elétrico?", ["Sim", "Não"]),
        C("has_hh_fuses", "Possui fusível HH?", ["Sim", "Não"]),
    ]
    if vals.get("has_hh_fuses") == "Sim":
        qs.append(T("hh_fuse_current", "Qual a Corrente do fusível HH?"))
    qs.append(C("circuit_breaker_type", "Tipo",
                ["A vácuo", "Cabinado", "PVO", "Não possui"],
                section="2. Disjuntor de Média Tensão:"))
    if vals.get("circuit_breaker_type") and vals.get("circuit_breaker_type") != "Não possui":
        qs += [
            T("circuit_breaker_manufacturer", "Fabricante"),
            T("circuit_breaker_serial_number", "Nº de Série"),
            T("circuit_breaker_rated_voltage_ur", "Tensão nominal (Ur)"),
            T("circuit_breaker_nbi_val", "Tensão nominal NBI (Ud ou Up)"),
        ]
    qs += [
        T("relay_manufacturer", "Fabricante", section="3. Relé de Proteção:"),
        T("relay_model", "Modelo"),
        T("relay_serial_number", "Nº de Série"),
        T("relay_rtc", "Relação dos TCs"),
        T("relay_rtp", "RTP"),
        T("ups_input_voltage", "Tensão de Entrada", section="Nobreak"),
        T("ups_output_voltage", "Tensão de Saída"),
        C("ups_status_normal", "Funcionamento está normal?", ["Sim", "Não"]),
    ]
    return qs


def s_transformer(vals: dict) -> list[Question]:
    qs = [C("is_dry_transformer", "O transformador é A seco?", ["Sim", "Não"])]
    if vals.get("is_dry_transformer") is None:
        return qs
    dry = vals.get("is_dry_transformer") == "Sim"

    qs += [
        T("power_rating", "Potência", section="1. Dados da Placa:"),
        T("manufacturer", "Fabricante"),
        T("serial_number", "Número de Série"),
        T("manufacturing_date", "Data de Fabricação"),
        T("total_mass", "Massa Total"),
    ]
    if not dry:
        qs.append(T("oil_volume", "Volume de Óleo"))
    qs.append(T("secondary_voltage", "Tensão do Secundário"))
    if not dry:
        qs.append(T("current_tap", "TAP Atual"))

    # 2. Status Visual
    first_visual = "Guarnições Primárias" if not dry else None
    if not dry:
        qs.append(C("primary_gaskets_status", "Guarnições Primárias",
                    ["OK", "OBS", "N/C"], section="2. Status Visual:"))
        if vals.get("primary_gaskets_status") == "OBS":
            qs.append(DESC("primary_gaskets_status"))
        qs.append(C("secondary_gaskets_status", "Guarnições Secundárias", ["Ok", "OBS", "N/C"]))
        if vals.get("secondary_gaskets_status") == "OBS":
            qs.append(DESC("secondary_gaskets_status"))
        qs.append(C("oil_level_status", "Nível de Óleo", ["OK", "OBS", "N/C"]))
        if vals.get("oil_level_status") == "OBS":
            qs.append(DESC("oil_level_status"))
        qs.append(C("has_oxidation_marks", "Marcas de Oxidação?", ["Sim", "Não"]))
    else:
        qs.append(C("has_oxidation_marks", "Marcas de Oxidação?",
                    ["Sim", "Não"], section="2. Status Visual:"))
    if not dry:
        qs.append(C("has_visible_oil_leak", "Vazamento de óleo visível?", ["Sim", "Não"]))
    qs.append(C("is_grounded_carcass_x0", "Aterrado na carcaça e no X0?", ["Sim", "Não"]))
    return qs


def s_general_protection(vals: dict) -> list[Question]:
    qs = [
        T("main_breaker_capacity", "Capacidade do Disjuntor Geral",
          section="1. Estrutura e Proteção:"),
        T("main_breaker_adjustment", "Ajuste (se houver)"),
        C("conductor_type", "Qual o tipo dos condutores?", ["Cabos", "Bus-Way"]),
    ]
    busway = vals.get("conductor_type") == "Bus-Way"
    if vals.get("conductor_type") is None or not busway:
        qs += [
            T("conductor_section_phase", "Seção do Condutor - Fase"),
            T("conductor_section_neutral", "Seção do Condutor - Neutro"),
            C("insulation_type", "Isolação (PVC ou EPR/XLPE)", ["PVC", "EPR/XLPE"]),
        ]
    qs += [
        T("grounding_resistance_ohms", "Aferição de aterramento (em Ohms)"),
        C("has_oxidation_marks", "Tem oxidação?", ["Sim", "Não"]),
        C("is_panel_grounded", "O quadro está aterrado?", ["Sim", "Não"]),
        T("voltage_r_s", "Tensão Fase-Fase — R-S", section="2. Medições de Tensão:"),
        T("voltage_s_t", "Tensão Fase-Fase — S-T"),
        T("voltage_r_t", "Tensão Fase-Fase — R-T"),
        T("voltage_r_n", "Tensão Fase-Neutro — R-N"),
        T("voltage_s_n", "Tensão Fase-Neutro — S-N"),
        T("voltage_t_n", "Tensão Fase-Neutro — T-N"),
        T("current_r", "Corrente — R"),
        T("current_s", "Corrente — S"),
        T("current_t", "Corrente — T"),
    ]
    return qs


def s_low_voltage(vals: dict) -> list[Question]:
    return [
        C("physical_protection_type", "Proteção Física", ["Policarbonato", "Metálica"]),
        C("has_oxidation_marks", "Há pontos de oxidação?", ["Sim", "Não"]),
        C("is_panel_grounded", "O quadro está aterrado?", ["Sim", "Não"]),
        T("voltage_r_s", "Tensão Fase-Fase — R-S", section="Medições de Tensão:"),
        T("voltage_s_t", "Tensão Fase-Fase — S-T"),
        T("voltage_r_t", "Tensão Fase-Fase — R-T"),
        T("voltage_r_n", "Tensão Fase-Neutro — R-N"),
        T("voltage_s_n", "Tensão Fase-Neutro — S-N"),
        T("voltage_t_n", "Tensão Fase-Neutro — T-N"),
        T("current_r", "Corrente — R"),
        T("current_s", "Corrente — S"),
        T("current_t", "Corrente — T"),
    ]


_CAP_CHARS_SECTION = "Por gentileza informe as seguintes características de cada um dos capacitores."


def _cap_chars() -> list[Question]:
    return [
        T("_cap_potencia", "Potência", section=_CAP_CHARS_SECTION),
        T("_cap_tensao", "Tensão"),
        T("_cap_corrente", "Corrente Fase A, Fase B, Fase C"),
    ]


def s_capacitor_bank(vals: dict) -> list[Question]:
    qs = [T("_bank_count", "Informe a quantidade de Bancos de capacitores")]
    count = vals.get("_bank_count")
    if count is None:
        return qs
    if "0" in str(count):
        # Banco inexistente: pula o restante (no Typebot vai direto ao próximo bot).
        return qs
    qs.append(C("activation_device_type", "Tipo", ["Timer", "Controlador", "Fixo"],
                section="1. Dispositivo de Acionamento:"))
    tipo = vals.get("activation_device_type")
    if tipo is None:
        return qs

    if tipo == "Timer":
        qs.append(T("cells_measurements_data", "Digite a quantidade de capacitores"))
        qs += _cap_chars()
    elif tipo == "Controlador":
        qs += [
            T("model", "Modelo"),
            T("manufacturer", "Fabricante"),
            T("outputs_count", "Nº de Saídas"),
            T("_tc_location", "Onde está instalado o TC?"),
            T("cells_measurements_data", "Digite a quantidade de capacitores"),
        ]
        qs += _cap_chars()
    elif tipo == "Fixo":
        qs += [
            T("model", "Qual a seção transversal do alimentador?"),
            T("manufacturer", "Qual o tipo de isolamento do alimentador?"),
            C("_fixo_protection_type", "Qual o tipo de proteção?",
              ["Disjuntor", "Fusível com Chave Seccionadora"]),
            T("general_protection_r", "Qual a Corrente da proteção?"),
            C("_other_protection", "Há outra proteção na origem do circuito?", ["Sim", "Não"]),
        ]
        if vals.get("_other_protection") == "Sim":
            qs += [
                T("_spec_tipo", "Especifique o tipo"),
                T("_spec_corrente", "Especifique a Corrente"),
                T("_spec_local", "Especifique a Localização"),
            ]
        qs.append(T("cells_measurements_data", "Digite a quantidade de capacitores"))
        qs += _cap_chars()
    return qs


def s_general_conditions(vals: dict) -> list[Question]:
    qs = [C("walls_ceiling_floor_status",
            "Paredes, Teto, Piso, Tapete ou estrado de borracha", ["OK", "OBS", "N/C"])]
    if vals.get("walls_ceiling_floor_status") == "OBS":
        qs.append(DESC("walls_ceiling_floor_status"))
    qs.append(C("emergency_lighting_status", "Iluminação de emergência", ["OK", "OBS", "N/C"]))
    if vals.get("emergency_lighting_status") == "OBS":
        qs.append(DESC("emergency_lighting_status"))
    qs += [
        T("ambient_temperature", "Temperatura Ambiente"),
        T("relative_humidity", "Umidade relativa do ar"),
        T("extinguisher_co2_status", "Extintor CO2", section="2. Segurança e Documentação:"),
        T("extinguisher_last_recharge", "Data da última recarga"),
        C("rubber_gloves_hv_status", "Luvas de Borracha (17,5 kV)", ["OK", "OBS"]),
    ]
    if vals.get("rubber_gloves_hv_status") == "OBS":
        qs.append(DESC("rubber_gloves_hv_status"))
    qs.append(C("gloves_box_status", "Há caixa de abrigo para elas?", ["Sim", "Não"]))
    qs.append(C("single_line_diagram_status", "Unifilar da SE e do QGBT", ["OK", "OBS", "N/C"]))
    if vals.get("single_line_diagram_status") == "OBS":
        qs.append(DESC("single_line_diagram_status"))
    qs += [
        C("warning_signs_status", "Placas de advertência em grades", ["Sim", "Não"]),
        C("are_gates_doors_grounded", "Grades e portas aterradas?", ["Sim", "Não"]),
        C("are_gates_doors_locked", "Grades e portas com trancas?", ["Sim", "Não"]),
        C("gates_doors_condition", "Condições de grades e portas", ["OK", "OBS", "NC"]),
    ]
    if vals.get("gates_doors_condition") == "OBS":
        qs.append(DESC("gates_doors_condition"))
    return qs


def s_additional_services(vals: dict) -> list[Question]:
    qs = [C("_has_extra",
            "Houve algum serviço extra ou manutenção corretiva realizada fora do escopo principal?",
            ["Sim", "Não"])]
    if vals.get("_has_extra") == "Sim":
        qs.append(T("description", "Descreva o serviço"))
    return qs


def s_general_observations(vals: dict) -> list[Question]:
    qs = [C("oil_collection_status", "A coleta de óleo foi realizada?",
            ["Sim", "Não"], section="1. Coleta de Óleo:")]
    if vals.get("oil_collection_status") == "Não":
        qs.append(T("oil_volume", "Descreva o motivo"))
    qs.append(T("general_notes", "Existe alguma observação geral sobre o serviço?",
               section="2. Observações e Pendências:"))
    qs.append(C("materials_needed_list", "Ficou alguma pendência de material?", ["Sim", "Não"]))
    if vals.get("materials_needed_list") == "Sim":
        qs.append(DESC("materials_needed_list", "Descreva os materiais necessários"))
    return qs


# --------------------------------------------------------------------------
# Definição das etapas
# --------------------------------------------------------------------------

@dataclass
class Step:
    key: str            # parte do checklist (registry)
    title: str
    intro: str
    build_script: Callable[[dict], list[Question]]
    instance_field: str | None = None
    instance: int = 1
    append_only: bool = False


STEPS: list[Step] = [
    Step("power_supply_input", "Entrada de Alimentação",
         "Vamos começar pela *Entrada de Alimentação*. ⚡", s_power_supply),
    Step("medium_voltage_protection", "Proteção em Média Tensão",
         "Agora vamos verificar a *Proteção em Média Tensão*. ⚡", s_medium_voltage),
    Step("transformer_inspection", "Transformador",
         "Muito bem! Vamos agora para a inspeção do *Transformador*. ⚡",
         s_transformer, instance_field="transformer_number"),
    Step("general_protection_panel", "Quadro de Proteção Geral",
         "Chegamos no *Quadro de Proteção Geral*! ⚡ Atenção aos números.",
         s_general_protection, instance_field="panel_number"),
    Step("low_voltage_main_panel", "Quadro Geral de Baixa Tensão",
         "Agora o *Quadro Geral de Baixa Tensão (QGBT)*. ⚡",
         s_low_voltage, instance_field="panel_number"),
    Step("capacitor_bank", "Banco de Capacitores",
         "Muito bem! Agora vamos verificar o *Banco de Capacitores*. ⚡", s_capacitor_bank),
    Step("general_conditions", "Condições Gerais",
         "Estamos quase terminando! Agora as *Condições Gerais* da subestação. ⚡",
         s_general_conditions),
    Step("additional_services_executed", "Serviços Executados",
         "Vamos registrar os *Serviços Executados*.", s_additional_services, append_only=True),
    Step("general_observations", "Observações Gerais",
         "Chegamos na etapa final: *Observações Gerais*! ⚡", s_general_observations),
]


# --------------------------------------------------------------------------
# Motor
# --------------------------------------------------------------------------

def derive_vals(records: list[dict]) -> dict:
    """records ordenados -> dict var->valor (entradas posteriores sobrescrevem)."""
    vals: dict = {}
    for r in records:
        vals[r["var"]] = r["value"]
    return vals


def next_question(step: Step, records: list[dict]) -> Question | None:
    vals = derive_vals(records)
    script = step.build_script(vals)
    answered = {r["qkey"] for r in records}
    for q in script:
        if q.qkey not in answered:
            return q
    return None


def current_step_and_question(records: list[dict], start_idx: int) -> tuple[int, Question | None]:
    """Avança a partir de `start_idx` até a primeira etapa com pergunta pendente.

    Retorna (idx, pergunta). Se idx == len(STEPS), o fluxo terminou (pergunta None).
    `records` deve conter a chave "step_idx" para filtrar por etapa.
    """
    idx = start_idx
    while idx < len(STEPS):
        recs = [r for r in records if r["step_idx"] == idx]
        q = next_question(STEPS[idx], recs)
        if q is None:
            idx += 1
            continue
        return idx, q
    return idx, None

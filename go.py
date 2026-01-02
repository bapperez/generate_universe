#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ==================================================
# Paths (4 JSONs)
# ==================================================

BASE_DIR = Path(__file__).parent

ASSETS_FILE = BASE_DIR / "assets.json"
SPACES_FILE = BASE_DIR / "spaces.json"
UNIVERSES_FILE = BASE_DIR / "universes.json"
CONFIG_FILE = BASE_DIR / "config.json"

OUTPUT_FILE = BASE_DIR / "prompt_out.txt"


# ==================================================
# ANSI + display width (wcwidth-like, sem dependência)
# ==================================================

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s or "")


def _char_width(ch: str) -> int:
    # Heurística “boa o bastante” sem dependência:
    # - CJK / Fullwidth / Emoji geralmente ocupam 2 colunas
    # - ASCII e a maioria das letras ocupam 1
    o = ord(ch)
    # controles
    if o == 0:
        return 0
    if o < 32 or 0x7F <= o < 0xA0:
        return 0

    # Faixas típicas de wide/fullwidth (CJK + símbolos + emoji)
    wide_ranges = [
        (0x1100, 0x115F),
        (0x2329, 0x232A),
        (0x2E80, 0xA4CF),
        (0xAC00, 0xD7A3),
        (0xF900, 0xFAFF),
        (0xFE10, 0xFE19),
        (0xFE30, 0xFE6F),
        (0xFF00, 0xFF60),
        (0xFFE0, 0xFFE6),
        (0x1F300, 0x1FAFF),  # emoji
        (0x20000, 0x3FFFD),
    ]
    for a, b in wide_ranges:
        if a <= o <= b:
            return 2
    return 1


def display_width(s: str) -> int:
    s = strip_ansi(s or "")
    return sum(_char_width(ch) for ch in s)


def pad_right(s: str, width: int) -> str:
    w = display_width(s)
    if w >= width:
        return s
    return s + (" " * (width - w))


# ==================================================
# JSON utils
# ==================================================


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON inválido em: {path}")
        print(f"   {e}")
        sys.exit(1)


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _title(s: str) -> str:
    s = (s or "").strip()
    return s[:1].upper() + s[1:] if s else s


def _safe_join(items: List[str], sep: str = ", ") -> str:
    clean = [i.strip() for i in items if isinstance(i, str) and i.strip()]
    return sep.join(clean)


def _klabel(key: str) -> str:
    return (key or "").replace("_", " ").strip()


def _value_to_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        # lista de strings / números simples
        flat = []
        for x in v:
            if isinstance(x, (str, int, float)):
                sx = str(x).strip()
                if sx:
                    flat.append(sx)
        return _safe_join(flat)
    if isinstance(v, dict):
        # evita “código” grande; faz resumo simples
        bits = []
        for kk, vv in v.items():
            txt = _value_to_text(vv)
            if txt:
                bits.append(f"{_klabel(kk)}: {txt}")
        return _safe_join(bits, " | ")
    return str(v).strip()


# ==================================================
# Data access (schemas elásticos)
# ==================================================


def get_assets(data: Any) -> List[Dict[str, Any]]:
    # aceita {"assets":[...]}, {"assets_registry":[...]}, {"registry":[...]} ou lista pura
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("assets", "assets_registry", "registry"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def get_spaces(data: Any) -> List[Dict[str, Any]]:
    # novo schema: {"spaces":[...], "clusters":[...]}
    if isinstance(data, dict):
        v = data.get("spaces")
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def get_clusters(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        v = data.get("clusters")
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def get_universes(data: Any) -> List[Dict[str, Any]]:
    # aceita {"universes":[...]} ou lista
    if isinstance(data, dict):
        v = data.get("universes")
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def get_config(data: Any) -> Dict[str, Any]:
    return data if isinstance(data, dict) else {}


# ==================================================
# Resolvers (aceitam ID ou nome)
# ==================================================


def resolve_space(spaces: List[Dict[str, Any]], token: str) -> Optional[Dict[str, Any]]:
    t = _norm(token)
    for s in spaces:
        if _norm(str(s.get("id", ""))) == t:
            return s
        if _norm(str(s.get("name", ""))) == t:
            return s
    return None


def resolve_universe(
    universes: List[Dict[str, Any]], token: str
) -> Optional[Dict[str, Any]]:
    t = _norm(token)
    for u in universes:
        if _norm(str(u.get("id", ""))) == t:
            return u
        if _norm(str(u.get("name", ""))) == t:
            return u
    return None


def resolve_assets(
    assets: List[Dict[str, Any]], tokens: List[str]
) -> List[Dict[str, Any]]:
    resolved: List[Dict[str, Any]] = []
    seen = set()
    for tok in tokens:
        t = _norm(tok)
        found = None
        for a in assets:
            aid = _norm(str(a.get("asset_id", "")))
            full = _norm(f"{a.get('nome', '')} {a.get('sobrenome', '')}".strip())
            if t == aid or t == full:
                found = a
                break
        if found:
            key = _norm(str(found.get("asset_id", "")) or full)
            if key not in seen:
                resolved.append(found)
                seen.add(key)
        else:
            print(f"⚠️ Ativo não encontrado: {tok}")
    return resolved


def resolve_cluster(
    clusters: List[Dict[str, Any]], cluster_id: str
) -> Optional[Dict[str, Any]]:
    t = _norm(cluster_id)
    for c in clusters:
        if _norm(str(c.get("cluster_id", ""))) == t:
            return c
    return None


# ==================================================
# CLI sanitização / tokens
# ==================================================


def _sanitize_argv(argv: List[str]) -> List[str]:
    # junta tudo, depois separa por espaços, vírgulas e "+"
    joined = " ".join(argv).strip()
    if not joined:
        return []
    joined = joined.replace("+", " ")
    parts = []
    for chunk in joined.split():
        # separa por vírgulas
        sub = [x.strip() for x in chunk.split(",") if x.strip()]
        parts.extend(sub)
    return parts


# ==================================================
# Dashboard (2 colunas)
# Coluna esquerda: Universos e Espaços
# Coluna direita: Ativos
# ==================================================

C_RESET = "\x1b[0m"
C_CYAN = "\x1b[36m"
C_BLUE = "\x1b[34m"
C_GRAY = "\x1b[90m"


def _hdr(text: str, color: str) -> str:
    return f"{color}{text}{C_RESET}"


def clear_screen() -> None:
    os.system("clear" if os.name != "nt" else "cls")


def build_left_column(
    universes: List[Dict[str, Any]], spaces: List[Dict[str, Any]]
) -> List[str]:
    lines: List[str] = []
    lines.append(_hdr("🌌 UNIVERSOS", C_BLUE))
    for u in universes:
        uid = str(u.get("id", "")).strip()
        name = str(u.get("name", "")).strip()
        if uid or name:
            lines.append(f"{uid:<5} {name}".rstrip())

    lines.append("")  # spacer
    lines.append(_hdr("📍 ESPAÇOS", C_BLUE))
    for s in spaces:
        sid = str(s.get("id", "")).strip()
        name = str(s.get("name", "")).strip()
        if sid or name:
            lines.append(f"{sid:<5} {name}".rstrip())
    return lines


def build_right_column(assets: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    lines.append(_hdr("👤 ATIVOS", C_BLUE))
    for a in assets:
        aid = str(a.get("asset_id", "")).strip()
        full = f"{a.get('nome', '')} {a.get('sobrenome', '')}".strip()
        if aid or full:
            lines.append(f"{aid:<5} {full}".rstrip())
    return lines


def print_dashboard(
    universes: List[Dict[str, Any]],
    spaces: List[Dict[str, Any]],
    assets: List[Dict[str, Any]],
) -> None:
    clear_screen()
    top = "┌──────────────────────── MATRIX :: CONSOLE ────────────────────────┐"
    mid = "│ STATUS: READY            MODE: GENERATOR           VERSION: 1.0   │"
    bot = "└───────────────────────────────────────────────────────────────────┘"
    print(_hdr(top, C_GRAY))
    print(_hdr(mid, C_GRAY))
    print(_hdr(bot, C_GRAY))
    print()

    left = build_left_column(universes, spaces)
    right = build_right_column(assets)

    left_width = max((display_width(x) for x in left), default=40) + 4
    rows = max(len(left), len(right))
    for i in range(rows):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        print(pad_right(l, left_width) + r)

    print()


# ==================================================
# Cluster attachment (apenas em SPACE / SPACE+ASSETS)
# ==================================================


def attach_cluster_if_needed(
    space: Dict[str, Any],
    clusters: List[Dict[str, Any]],
    assets_count: int,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    binding = space.get("cluster_binding")
    if not isinstance(binding, dict):
        return None, None

    cluster_id = str(binding.get("cluster_id", "")).strip()
    inherits = bool(binding.get("inherits_contract", False))
    requires = bool(binding.get("requires_cluster_validation", False))

    if not cluster_id:
        return None, None

    cluster = resolve_cluster(clusters, cluster_id)
    if not cluster and requires:
        print(
            f"❌ Space exige cluster {cluster_id}, mas ele não existe em spaces.json."
        )
        sys.exit(1)

    if not cluster or not inherits:
        return cluster, None

    # variação inferida
    if assets_count >= 2:
        variation = "duo"
    else:
        # 0 ou 1 → assume solo (o schema define a regra por ativos; sem ativos, é solo por padrão)
        variation = "solo"

    return cluster, variation


# ==================================================
# Prompt rendering (sem IDs, linguagem humana)
# ==================================================


def describe_universe(u: Dict[str, Any]) -> str:
    name = str(u.get("name", "")).strip() or "Universo sem nome"
    lines: List[str] = []
    lines.append("## UNIVERSO ATIVO")
    lines.append("")
    lines.append(f"**{name}**")
    lines.append("")

    # imprime metadados do universo, sem despejar JSON
    meta_keys = [
        "classification",
        "temporal_policy",
        "memory_policy",
        "safety_envelope",
        "tone",
        "genre",
        "year",
        "setting",
        "rules",
        "limits",
        "notes",
    ]
    bits = []
    for k in meta_keys:
        if k in u:
            txt = _value_to_text(u.get(k))
            if txt:
                bits.append(f"- {_title(_klabel(k))}: {txt}")
    if bits:
        lines.append("### Metadados")
        lines.extend(bits)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def describe_space(
    space: Dict[str, Any], cluster: Optional[Dict[str, Any]], variation: Optional[str]
) -> str:
    name = str(space.get("name", "")).strip() or "Espaço sem nome"
    lines: List[str] = []
    lines.append("## ESPAÇO ATIVO")
    lines.append("")
    lines.append(f"**{name}**")
    lines.append("")

    # cluster metadata (se aplicável)
    if cluster:
        cname = (
            str(cluster.get("name", "")).strip()
            or str(cluster.get("cluster_id", "")).strip()
        )
        cdesc = str(cluster.get("description", "")).strip()
        lines.append("### Cluster (contrato transversal)")
        lines.append(f"- Nome: {cname}")
        if cdesc:
            lines.append(f"- Descrição: {cdesc}")
        if variation:
            lines.append(
                f"- Variação inferida: {variation} (pela quantidade de ativos)"
            )
        lines.append("")

        contract = cluster.get("contract")
        if isinstance(contract, dict):
            core = contract.get("core_principles")
            forb = contract.get("forbidden_outcomes")
            req = contract.get("execution_requirements")

            if isinstance(core, list) and core:
                lines.append("**Princípios do cluster (sempre presentes):**")
                for x in core:
                    if isinstance(x, str) and x.strip():
                        lines.append(f"- {x.strip()}")
                lines.append("")

            if isinstance(forb, list) and forb:
                lines.append("**Proibido no cluster:**")
                for x in forb:
                    if isinstance(x, str) and x.strip():
                        lines.append(f"- {x.strip()}")
                lines.append("")

            if isinstance(req, dict) and req:
                lines.append("**Requisitos mínimos de execução:**")
                for kk, vv in req.items():
                    txt = _value_to_text(vv)
                    if txt:
                        lines.append(f"- {_klabel(kk)}: {txt}")
                lines.append("")

        # variations no cluster (somente como possibilidade; não cria modo novo)
        vars_ = cluster.get("variations")
        if isinstance(vars_, dict) and vars_:
            lines.append("**Variações possíveis (schema):**")
            for vname, vobj in vars_.items():
                if not vname:
                    continue
                if isinstance(vobj, dict) and vobj:
                    desc = _value_to_text(vobj)
                    if desc:
                        lines.append(f"- {vname}: {desc}")
                    else:
                        lines.append(f"- {vname}")
                else:
                    lines.append(f"- {vname}")
            lines.append("")

    # campos semânticos do space: preserva, sem virar “código”
    skip = {"id", "cluster_binding"}  # nunca expor id
    preferred = [
        "type",
        "mode",
        "description",
        "objects",
        "rules",
        "biomechanics",
        "balance_model",
        "leverage_model",
        "erotization_level",
        "wardrobe_policy",
        "variation_descriptions",
        "cold_open",
        "camera",
        "lighting",
        "sound",
        "music",
    ]

    bullets: List[str] = []
    for k in preferred:
        if k in space and k not in skip:
            txt = _value_to_text(space.get(k))
            if txt:
                bullets.append(f"- {_title(_klabel(k))}: {txt}")

    # inclui extras desconhecidos (elasticidade), mas só se forem simples
    extras = []
    for k, v in space.items():
        if k in skip or k in preferred:
            continue
        txt = _value_to_text(v)
        if txt:
            extras.append(f"- {_title(_klabel(k))}: {txt}")

    if bullets or extras:
        lines.append("### Parâmetros do espaço (base para execução)")
        lines.extend(bullets)
        lines.extend(extras)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def describe_asset(a: Dict[str, Any]) -> str:
    nome = str(a.get("nome", "")).strip()
    sobrenome = str(a.get("sobrenome", "")).strip()
    full = f"{nome} {sobrenome}".strip() or "Ativo sem nome"

    nasc = str(a.get("data_nascimento", "")).strip()
    signo = str(a.get("signo", "")).strip()
    altura = a.get("altura_cm", None)
    peso = a.get("peso_kg", None)
    idade = a.get("idade", None)

    cabelo = str(a.get("cor_cabelo", "")).strip()
    corte = str(a.get("corte_penteado", "")).strip()
    pele = str(a.get("cor_pele", "")).strip()
    olhos = str(a.get("cor_olhos", "")).strip()

    estrutura = str(a.get("estrutura_corpo", "")).strip()
    tecido = a.get("tecido_adiposo", None)
    musc = a.get("musculatura", None)

    personalidade = str(a.get("personalidade", "")).strip()
    asc = str(a.get("ascendente", "")).strip()
    asc_conf = a.get("ascendente_confianca", None)

    bits = []
    # dados
    dados = []
    if nasc:
        dados.append(f"nascimento {nasc}")
    if isinstance(idade, int):
        dados.append(f"idade {idade}")
    if signo:
        dados.append(f"signo {signo}")
    if isinstance(altura, int):
        dados.append(f"altura {altura} cm")
    if isinstance(peso, (int, float)):
        dados.append(f"peso {peso} kg")

    if dados:
        bits.append(f"- Dados: " + "; ".join(dados))

    # aparência
    apar = []
    if cabelo:
        apar.append(f"cabelo {cabelo}")
    if corte:
        apar.append(f"corte {corte}")
    if pele:
        apar.append(f"pele {pele}")
    if olhos:
        apar.append(f"olhos {olhos}")
    if apar:
        bits.append(f"- Aparência: " + "; ".join(apar))

    # corpo
    corpo = []
    if estrutura:
        corpo.append(estrutura)
    if isinstance(tecido, int):
        corpo.append(f"tecido adiposo {tecido}/100")
    if isinstance(musc, int):
        corpo.append(f"musculatura {musc}/100")
    if corpo:
        bits.append(f"- Corpo: " + " — ".join(corpo))

    # personalidade / ascendente
    pers = []
    if personalidade:
        pers.append(personalidade)
    if asc:
        if isinstance(asc_conf, int):
            pers.append(f"ascendente {asc} (confiança {asc_conf}/100)")
        else:
            pers.append(f"ascendente {asc}")
    if pers:
        bits.append(f"- Personalidade: " + " | ".join(pers))

    # vestuário (regra fixa do sistema)
    bits.append(
        "- Vestuário: marcas premium e bonitas, escolhidas livremente conforme o contexto (o figurino responde ao ambiente)."
    )

    return f"- **{full}**\n" + "\n".join(bits)


def render_assets_block(selected_assets: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("## ATIVOS PRESENTES")
    lines.append("")
    for a in selected_assets:
        lines.append(describe_asset(a))
    lines.append("")
    return "\n".join(lines)


def render_direction_block() -> str:
    return "\n".join(
        [
            "## DIREÇÃO CRIATIVA (liberdade do Gemini)",
            "",
            "- Use as informações como base e expanda com criatividade, sem travar em formato.",
            "- Você pode criar espaços, detalhes e dinâmica social quando necessário para o mundo funcionar.",
            "- Não liste IDs/códigos no texto. Trate tudo como descrição humana e visual.",
            "- Continuidade pode ser local ao chat; um novo prompt pode redefinir o setup.",
            "- A pausa e o silêncio também são conteúdo.",
            "",
        ]
    )


def generate_prompt_universe_only(u: Dict[str, Any]) -> str:
    title = "MATRIX — PROMPT GERADOR (UNIVERSO)"
    return (
        "\n".join([title, "", describe_universe(u), render_direction_block()]).strip()
        + "\n"
    )


def generate_prompt_space_only(
    space: Dict[str, Any], cluster: Optional[Dict[str, Any]], variation: Optional[str]
) -> str:
    title = "MATRIX — PROMPT GERADOR (ESPAÇO)"
    return (
        "\n".join(
            [
                title,
                "",
                describe_space(space, cluster, variation),
                render_direction_block(),
            ]
        ).strip()
        + "\n"
    )


def generate_prompt_assets_only(selected_assets: List[Dict[str, Any]]) -> str:
    title = "MATRIX — PROMPT GERADOR (ATIVOS)"
    return (
        "\n".join(
            [title, "", render_assets_block(selected_assets), render_direction_block()]
        ).strip()
        + "\n"
    )


def generate_prompt_universe_with_assets(
    u: Dict[str, Any], selected_assets: List[Dict[str, Any]]
) -> str:
    title = "MATRIX — PROMPT GERADOR (UNIVERSO + ATIVOS)"
    return (
        "\n".join(
            [
                title,
                "",
                describe_universe(u),
                render_assets_block(selected_assets),
                render_direction_block(),
            ]
        ).strip()
        + "\n"
    )


def generate_prompt_space_with_assets(
    space: Dict[str, Any],
    cluster: Optional[Dict[str, Any]],
    variation: Optional[str],
    selected_assets: List[Dict[str, Any]],
) -> str:
    title = "MATRIX — PROMPT GERADOR (ESPAÇO + ATIVOS)"
    return (
        "\n".join(
            [
                title,
                "",
                describe_space(space, cluster, variation),
                render_assets_block(selected_assets),
                render_direction_block(),
            ]
        ).strip()
        + "\n"
    )


# ==================================================
# Mode detection (não assume primeiro argumento)
# ==================================================


def detect_mode(
    universes: List[Dict[str, Any]],
    spaces: List[Dict[str, Any]],
    assets: List[Dict[str, Any]],
    tokens: List[str],
) -> Tuple[
    str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]]
]:
    """
    Retorna:
      mode: universe_only | space_only | assets_only | universe_assets | space_assets
      u: universe or None
      s: space or None
      selected_assets: list
    """
    if not tokens:
        return ("list", None, None, [])

    # tenta capturar universe/space em qualquer posição
    u = None
    s = None
    remaining: List[str] = []

    for t in tokens:
        if u is None:
            u_try = resolve_universe(universes, t)
            if u_try:
                u = u_try
                continue
        if s is None:
            s_try = resolve_space(spaces, t)
            if s_try:
                s = s_try
                continue
        remaining.append(t)

    # resolve ativos dos remanescentes
    selected_assets = resolve_assets(assets, remaining) if remaining else []

    # decisão final
    if u and not s:
        if selected_assets:
            return ("universe_assets", u, None, selected_assets)
        return ("universe_only", u, None, [])
    if s and not u:
        if selected_assets:
            return ("space_assets", None, s, selected_assets)
        return ("space_only", None, s, [])
    if (not u) and (not s):
        if selected_assets:
            # IMPORTANT: suporta 1 ou N ativos (corrige o bug do N>=2)
            return ("assets_only", None, None, selected_assets)

    return ("invalid", u, s, selected_assets)


# ==================================================
# Main
# ==================================================


def main() -> None:
    spaces_data = load_json(SPACES_FILE)
    universes_data = load_json(UNIVERSES_FILE)
    assets_data = load_json(ASSETS_FILE)
    config = get_config(load_json(CONFIG_FILE)) if CONFIG_FILE.exists() else {}

    spaces = get_spaces(spaces_data)
    clusters = get_clusters(spaces_data)
    universes = get_universes(universes_data)
    assets = get_assets(assets_data)

    # sem parâmetros → dashboard
    if len(sys.argv) == 1:
        print_dashboard(universes, spaces, assets)
        return

    tokens = _sanitize_argv(sys.argv[1:])
    mode, u, s, selected_assets = detect_mode(universes, spaces, assets, tokens)

    # gera prompt
    if mode == "universe_only" and u:
        prompt = generate_prompt_universe_only(u)

    elif mode == "space_only" and s:
        cluster, variation = attach_cluster_if_needed(s, clusters, assets_count=0)
        prompt = generate_prompt_space_only(s, cluster, variation)

    elif mode == "assets_only":
        if not selected_assets:
            print("❌ Nenhum ativo válido encontrado.")
            sys.exit(1)
        prompt = generate_prompt_assets_only(selected_assets)

    elif mode == "universe_assets" and u:
        if not selected_assets:
            print("❌ Nenhum ativo válido encontrado para este universo.")
            sys.exit(1)
        prompt = generate_prompt_universe_with_assets(u, selected_assets)

    elif mode == "space_assets" and s:
        if not selected_assets:
            print("❌ Nenhum ativo válido encontrado para este espaço.")
            sys.exit(1)
        cluster, variation = attach_cluster_if_needed(
            s, clusters, assets_count=len(selected_assets)
        )
        prompt = generate_prompt_space_with_assets(
            s, cluster, variation, selected_assets
        )

    else:
        print("❌ Uso inválido.")
        print("Exemplos:")
        print("  python3 go.py")
        print("  python3 go.py U-04")
        print("  python3 go.py S-11")
        print("  python3 go.py A-13,A-09")
        print("  python3 go.py U-04 A-09,A-10")
        print("  python3 go.py S-11 A-03,A-05")
        print("  python3 go.py U-04 + A-09")
        sys.exit(1)

    # salva prompt
    OUTPUT_FILE.write_text(prompt, encoding="utf-8")

    # mensagem de pós-save (com path seguro para espaços)
    # out_quoted = shlex.quote(str(OUTPUT_FILE))
    # print(f"\n💾 Prompt salvo | less -R {out_quoted}\n")
    # os.system('less -R "prompt_out.txt"')

    if sys.stdout.isatty() and shutil.which("less"):
        os.system(f"less -R prompt_out.txt")
    else:
        os.system(f"cat prompt_out.txt")


if __name__ == "__main__":
    main()

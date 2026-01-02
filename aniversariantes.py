#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ==========================
# CONFIG (novo padrão)
# ==========================

BASE_DIR = Path(__file__).parent
ASSETS_FILE = BASE_DIR / "assets.json"


# ==========================
# CONSTANTES
# ==========================

MESES_PT = {
    1: "JANEIRO",
    2: "FEVEREIRO",
    3: "MARÇO",
    4: "ABRIL",
    5: "MAIO",
    6: "JUNHO",
    7: "JULHO",
    8: "AGOSTO",
    9: "SETEMBRO",
    10: "OUTUBRO",
    11: "NOVEMBRO",
    12: "DEZEMBRO",
}


# ==========================
# JSON tolerant loader
# ==========================

_COMMENT_RE = re.compile(r"(^|\s)//.*?$|(^|\s)#.*?$", re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def sanitize_json(text: str) -> str:
    text = re.sub(_COMMENT_RE, "", text)
    text = re.sub(_TRAILING_COMMA_RE, r"\1", text)
    return text


def load_json(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    clean = sanitize_json(raw)
    return json.loads(clean)


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ==========================
# ASSETS: compat com vários formatos
# ==========================


def _extract_assets_container(data: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Retorna (lista_assets, key_container).
    - Se assets.json for uma LISTA: key_container = None (salvar direto a lista).
    - Se for um DICT, tenta chaves comuns: "assets", "assets_registry", "items".
    """
    if isinstance(data, list):
        # lista pura
        assets = [x for x in data if isinstance(x, dict)]
        return assets, None

    if isinstance(data, dict):
        for key in ("assets", "assets_registry", "items"):
            if isinstance(data.get(key), list):
                assets = [x for x in data.get(key, []) if isinstance(x, dict)]
                return assets, key

    # fallback: nada reconhecido
    return [], None


def load_assets() -> Tuple[Any, List[Dict[str, Any]], Optional[str]]:
    """
    Retorna (raw_data, assets_list, container_key)
    """
    data = load_json(ASSETS_FILE)
    assets, key = _extract_assets_container(data)
    return data, assets, key


# ==========================
# CORE UTILITIES
# ==========================


def parse_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


def calcular_idade(data_nasc: datetime, hoje: datetime) -> int:
    idade = hoje.year - data_nasc.year
    if (hoje.month, hoje.day) < (data_nasc.month, data_nasc.day):
        idade -= 1
    return idade


# ==========================
# LISTAGENS
# ==========================


def aniversariantes_mes(assets: List[Dict[str, Any]], mes: int) -> List[Dict[str, Any]]:
    hoje = datetime.today()
    resultados: List[Dict[str, Any]] = []

    for a in assets:
        dt = parse_date(str(a.get("data_nascimento", "")).strip())
        if not dt or dt.month != mes:
            continue

        resultados.append(
            {
                "nome": a.get("nome", "") or "",
                "sobrenome": a.get("sobrenome", "") or "",
                "data": dt,
                "idade": calcular_idade(dt, hoje),
            }
        )

    # dia crescente; dentro do dia, mais velho -> mais novo
    return sorted(resultados, key=lambda x: (x["data"].day, -x["idade"]))


def aniversariantes_ano(assets: List[Dict[str, Any]]):
    hoje = datetime.today()
    calendario = defaultdict(lambda: defaultdict(list))

    for a in assets:
        dt = parse_date(str(a.get("data_nascimento", "")).strip())
        if not dt:
            continue

        calendario[dt.month][dt.day].append(
            {
                "nome": a.get("nome", "") or "",
                "sobrenome": a.get("sobrenome", "") or "",
                "data": dt,
                "idade": calcular_idade(dt, hoje),
            }
        )

    # mais velho -> mais novo em cada dia
    for mes in calendario:
        for dia in calendario[mes]:
            calendario[mes][dia].sort(key=lambda x: -x["idade"])

    return calendario


# ==========================
# NOVA ROTINA — ATUALIZAR IDADES (sobrescreve "idade" no assets.json)
# ==========================


def atualizar_idades() -> None:
    hoje = datetime.today()

    raw_data, assets, container_key = load_assets()
    if not assets:
        print("❌ Nenhum ativo encontrado em assets.json.")
        sys.exit(1)

    atualizados = 0
    for a in assets:
        dt = parse_date(str(a.get("data_nascimento", "")).strip())
        if not dt:
            continue
        a["idade"] = calcular_idade(dt, hoje)
        atualizados += 1

    # re-injeta no container original
    if container_key is None:
        # lista pura
        raw_data = assets
    else:
        raw_data[container_key] = assets

    save_json(ASSETS_FILE, raw_data)

    print("✅ Idades atualizadas com sucesso.")
    print(f"👤 Total de ativos atualizados: {atualizados}")
    print(f"💾 Arquivo atualizado: {ASSETS_FILE.resolve()}")


# ==========================
# OUTPUT
# ==========================


def print_mes(resultados: List[Dict[str, Any]], mes: int) -> None:
    if not resultados:
        print("🎂 Nenhum aniversariante encontrado.\n")
        return

    print(f"\n📅 ANIVERSARIANTES DE {MESES_PT[mes]}\n")
    print(f"{'Dia':<5} {'Nome':<15} {'Sobrenome':<20} {'Nascimento':<12} {'Idade'}")
    print("-" * 70)

    for r in resultados:
        dia = r["data"].day
        print(
            f"{dia:<5} "
            f"{r['nome']:<15} "
            f"{r['sobrenome']:<20} "
            f"{r['data'].strftime('%d/%m/%Y'):<12} "
            f"{r['idade']}"
        )
    print()


def print_ano(calendario) -> None:
    if not calendario:
        print("🎂 Nenhum aniversariante encontrado.\n")
        return

    print("\n📆 CALENDÁRIO ANUAL DE ANIVERSÁRIOS\n")

    for mes in range(1, 13):
        if mes not in calendario:
            continue

        print(f"\n🗓️  MÊS DE {MESES_PT[mes]}")
        print(f"{'Dia':<5} {'Nome':<15} {'Sobrenome':<20} {'Nascimento':<12} {'Idade'}")
        print("-" * 70)

        for dia in sorted(calendario[mes]):
            for r in calendario[mes][dia]:
                print(
                    f"{dia:<5} "
                    f"{r['nome']:<15} "
                    f"{r['sobrenome']:<20} "
                    f"{r['data'].strftime('%d/%m/%Y'):<12} "
                    f"{r['idade']}"
                )


# ==========================
# CLI
# ==========================


def print_usage() -> None:
    print("\nUso:")
    print("  python3 aniversariantes.py mes_atual")
    print("  python3 aniversariantes.py mes_03")
    print("  python3 aniversariantes.py ano")
    print("  python3 aniversariantes.py ano_atual")
    print("  python3 aniversariantes.py atualizar_idades\n")


def main() -> None:
    if not ASSETS_FILE.exists():
        print("❌ assets.json não encontrado.")
        print(f"   Esperado em: {ASSETS_FILE.resolve()}")
        sys.exit(1)

    if len(sys.argv) != 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1].lower().strip()
    hoje = datetime.today()

    _, assets, _ = load_assets()
    if not assets and cmd != "atualizar_idades":
        print("❌ Nenhum ativo carregado de assets.json.")
        sys.exit(1)

    if cmd == "mes_atual":
        print_mes(aniversariantes_mes(assets, hoje.month), hoje.month)

    elif cmd.startswith("mes_"):
        try:
            mes = int(cmd.split("_", 1)[1])
            if not 1 <= mes <= 12:
                raise ValueError
            print_mes(aniversariantes_mes(assets, mes), mes)
        except ValueError:
            print("❌ Mês inválido.")
            sys.exit(1)

    elif cmd in ("ano", "ano_atual"):
        print_ano(aniversariantes_ano(assets))

    elif cmd == "atualizar_idades":
        atualizar_idades()

    else:
        print("❌ Comando desconhecido.")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()

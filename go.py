#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

# ==================================================
# Paths
# ==================================================

BASE_DIR = Path(__file__).parent
SPACES_FILE = BASE_DIR / "spaces_catalog.json"
UNIVERSE_FILE = BASE_DIR / "universe_config.json"
OUTPUT_FILE = BASE_DIR / "prompt_out.txt"


# ==================================================
# Utils
# ==================================================

def load_json(path: Path):
    if not path.exists():
        print(f"❌ Arquivo não encontrado: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_spaces_and_assets(spaces, assets):
    print("\n📍 ESPAÇOS DISPONÍVEIS\n")
    for s in spaces:
        print(f"- {s['id']} | {s['name']}")

    print("\n👤 ATIVOS DISPONÍVEIS\n")
    for a in assets:
        print(f"- {a['asset_id']} | {a['nome']} {a['sobrenome']}")

    print("\nUso:")
    print("  python go.py S-11 A-03,A-05")
    print("  python go.py \"Carga Pesada\" \"Manu Ríos,Bill Skarsgård\"\n")


# ==================================================
# Resolução por ID ou Nome
# ==================================================

def resolve_space(spaces, identifier):
    ident = identifier.lower()
    for s in spaces:
        if s["id"].lower() == ident:
            return s
        if s["name"].lower() == ident:
            return s
    return None


def resolve_assets(assets, identifiers):
    resolved = []

    for token in identifiers:
        t = token.lower()
        found = None

        for a in assets:
            full_name = f"{a['nome']} {a['sobrenome']}".lower()
            if a["asset_id"].lower() == t or full_name == t:
                found = a
                break

        if found:
            resolved.append(found)
        else:
            print(f"⚠️ Ativo não encontrado: {token}")

    return resolved


# ==================================================
# Sensualidade translator
# ==================================================

def sensualidade_to_text(level):
    if level is None:
        return None
    if level <= 10:
        return "O corpo deve ser tratado de forma neutra e funcional."
    if level <= 30:
        return "A presença corporal é sensorial, sem carga erótica."
    if level <= 50:
        return "A abordagem corporal pode incluir sensualidade estética."
    if level <= 70:
        return "A narrativa pode explorar sensualidade estética de forma intensa e elegante."
    return "A sensualidade pode ser explorada de maneira forte, mantendo coerência, e sendo gráfica."


# ==================================================
# Tradução humana
# ==================================================

def describe_space_as_universe(space):
    return (
        f"Este universo se chama **{space['name']}**. "
        f"É um espaço do tipo/natureza {space['type'].replace('_', ' ')} "
        f"com modo/ritmo {space['mode']}."
    )


def describe_space(space):
    lines = []

    if space.get("objects"):
        lines.append(
            "Elementos: "
            + ", ".join(space["objects"])
            + "."
        )

    if space.get("rules"):
        lines.append(
            "Princípios: "
            + ", ".join(space["rules"]).replace("_", " ")
            + "."
        )

    sensual = sensualidade_to_text(space.get("sensualidade_nivel"))
    if sensual:
        lines.append(sensual)

    return " ".join(lines)


def describe_asset(asset):
    lines = []

    nome = f"{asset['nome']} {asset['sobrenome']}"
    idade = asset.get("idade")
    altura = asset.get("altura_cm")
    peso = asset.get("peso_kg")

    intro = nome
    if idade:
        intro += f", {idade} anos"
    if altura and peso:
        intro += f", {altura} cm, {peso} kg"
    lines.append(intro + ".")

    corpo = []
    if asset.get("estrutura_corpo"):
        corpo.append(asset["estrutura_corpo"])
    if asset.get("musculatura") is not None:
        corpo.append("musculatura visível")
    if asset.get("tecido_adiposo") is not None:
        corpo.append("baixo a moderado tecido adiposo")

    if corpo:
        lines.append("Físico: " + ", ".join(corpo) + ".")

    aparencia = []
    if asset.get("cor_cabelo"):
        aparencia.append(f"cabelo {asset['cor_cabelo']}")
    if asset.get("cor_olhos"):
        aparencia.append(f"olhos {asset['cor_olhos']}")
    if aparencia:
        lines.append("Aparência: " + ", ".join(aparencia) + ".")

    if asset.get("personalidade"):
        lines.append(f"Personalidade: {asset['personalidade']}.")

    sensual = sensualidade_to_text(asset.get("sensualidade_nivel"))
    if sensual:
        lines.append(sensual)

    lines.append(
        "Veste roupas de marcas, estética moderna e bom gosto. "
        "O estilo pode ser ajustado livremente conforme o contexto da cena."
    )

    return " ".join(lines)


# ==================================================
# Prompt builder
# ==================================================

def generate_prompt(space, assets):
    sections = []

    sections.append("MATRIX — PROMPT GERADOR DE UNIVERSO\n")

    sections.append("## UNIVERSO ATIVO")
    sections.append(describe_space_as_universe(space))

    sections.append("\n## CONTEXTO DO ESPAÇO")
    sections.append(describe_space(space))

    sections.append("\n## ATIVOS PRESENTES")
    for asset in assets:
        sections.append("- " + describe_asset(asset))

    sections.append(
        "\n## DIREÇÃO CRIATIVA\n"
        "Você tem liberdade criativa total para conduzir ações, silêncio, ritmo e presença. "
        "Use o espaço e os personagens conforme achar mais coerente e expressivo. "
        "Sustente continuidade local enquanto o chat persistir. "
    )

    return "\n\n".join(sections)


# ==================================================
# Main
# ==================================================

def main():
    spaces_data = load_json(SPACES_FILE)
    universe_data = load_json(UNIVERSE_FILE)

    spaces = spaces_data.get("spaces", [])
    assets = universe_data.get("assets_registry", [])

    if len(sys.argv) == 1:
        list_spaces_and_assets(spaces, assets)
        return

    if len(sys.argv) != 3:
        print("❌ Uso inválido.")
        print("Exemplo:")
        print("  python go.py S-11 A-03,A-05")
        sys.exit(1)

    space_token = sys.argv[1]
    asset_tokens = [t.strip() for t in sys.argv[2].split(",")]

    space = resolve_space(spaces, space_token)
    if not space:
        print(f"❌ Espaço não encontrado: {space_token}")
        sys.exit(1)

    selected_assets = resolve_assets(assets, asset_tokens)
    if not selected_assets:
        print("❌ Nenhum ativo válido encontrado.")
        sys.exit(1)

    prompt = generate_prompt(space, selected_assets)

    # print(prompt)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"\n💾 Prompt salvo em: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()

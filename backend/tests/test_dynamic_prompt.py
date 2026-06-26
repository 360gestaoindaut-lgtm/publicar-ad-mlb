from app.services.ai.prompts import build_title_prompt, _resolve_structure


def test_resolve_structure_substitutes_all_tokens():
    result = _resolve_structure(
        "{referencia_tecnica} {marca}",
        {"technical_reference": "6203 DDU C3", "sku_brand": "NSK"},
    )
    assert result == "6203 DDU C3 NSK"


def test_resolve_structure_skips_empty_tokens():
    result = _resolve_structure(
        "{referencia_tecnica} {aplicacao_veiculo} {marca}",
        {"technical_reference": "6203 DDU C3", "vehicle_application": "", "sku_brand": "NSK"},
    )
    assert result == "6203 DDU C3 NSK"


def test_resolve_structure_no_leftover_braces():
    result = _resolve_structure("{cor} {marca}", {"sku_brand": "NSK"})
    assert "{" not in result
    assert result == "NSK"


def test_build_title_prompt_includes_custom_structure():
    config = {"structure": "{referencia_tecnica} {marca}", "rules": "Códigos técnicos são intocáveis."}
    prompt = build_title_prompt(
        sku_description="Rolamentos 6203 Ddu C3 NSK",
        sku_brand="NSK",
        condition="new",
        title_config=config,
        technical_reference="6203 DDU C3",
    )
    assert "6203 DDU C3 NSK" in prompt
    assert "Códigos técnicos são intocáveis" in prompt


def test_build_title_prompt_no_config_uses_static_fallback():
    prompt = build_title_prompt(
        sku_description="Rolamentos 6203 Ddu C3 NSK",
        sku_brand="NSK",
        condition="new",
        title_config=None,
    )
    # Static fallback: prompt should still be valid and reference the product
    assert "Rolamentos 6203 Ddu C3 NSK" in prompt
    assert "NSK" in prompt


def test_build_title_prompt_batch_mode_returns_single_json_instruction():
    prompt = build_title_prompt(
        sku_description="Rolamento 6203",
        sku_brand="NSK",
        condition="new",
        batch_mode=True,
    )
    assert '"title"' in prompt
    assert '"titles"' not in prompt

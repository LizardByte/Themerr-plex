"""Extract application messages while excluding bundled third-party browser code."""

from pathlib import Path

from babel.messages.extract import extract_from_dir
from babel.messages.frontend import parse_mapping_cfg


def test_extraction_skips_compiled_assets(tmp_path):
    web = tmp_path / 'web'
    (web / 'js').mkdir(parents=True)
    (web / 'assets').mkdir()
    (web / 'js' / 'config.js').write_text("_('Save changes');", encoding='utf-8')
    (web / 'assets' / 'api_docs.js').write_text("_('Minified third-party code');", encoding='utf-8')
    mapping = Path(__file__).resolve().parents[2] / 'scripts' / 'babel.cfg'
    with mapping.open(encoding='utf-8') as stream:
        methods, options = parse_mapping_cfg(stream)
    messages = list(extract_from_dir(str(web), method_map=methods, options_map=options))
    assert [message[2] for message in messages] == ['Save changes']

"""Generate a static, offline welcome page from editable HTML, CSS and shared data."""
import argparse
import html
import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT/'includes.chroot/usr/share/rova'
SPEC = importlib.util.spec_from_file_location('kestrel_experience', ROOT/'includes.chroot/usr/local/lib/kestrel/experience.py')
experience = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experience)


def render(profile='niri', directory=DATA):
    directory = pathlib.Path(directory)
    brand, center, shortcuts = experience.load_content(directory)
    if profile not in experience.PROFILES:
        raise ValueError('Unknown desktop profile: '+profile)
    values = {key: html.escape(value, quote=True) for key, value in brand.items()}
    values['desktop_guide'] = html.escape(center['desktop_guides'][profile])
    values['shortcuts'] = '\n'.join('<tr><td><kbd>'+html.escape(item['keys'])+'</kbd></td><td>'+
                                  html.escape(item['label'])+'</td></tr>'
                                  for item in experience.for_profile(shortcuts, profile))
    guides = json.loads((directory/'welcome-profiles.json').read_text(encoding='utf-8'))
    for target in experience.PROFILES:
        for field in ('backup', 'recovery'):
            if not isinstance(guides.get(target, {}).get(field), str) or not guides[target][field].strip():
                raise ValueError(f'welcome-profiles.json: missing {target} {field} guide')
    values['backup_guide'] = html.escape(guides[profile]['backup'])
    values['recovery_guide'] = html.escape(guides[profile]['recovery'])
    template = (directory/'welcome.template.html').read_text(encoding='utf-8')
    def replace(match):
        key = match[1]
        if key not in values:
            raise ValueError('Unknown welcome template token: '+key)
        return values[key]
    return re.sub(r'\{\{([a-z_]+)\}\}', replace, template)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=experience.PROFILES, default='niri')
    parser.add_argument('--output', type=pathlib.Path, default=DATA/'welcome.html')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args.profile), encoding='utf-8')
    print('Rendered '+str(args.output))

"""Shared, data-only desktop content. GTK and the offline website use this API."""
import json
import os
import pathlib

DATA = pathlib.Path('/usr/share/rova')
PROFILES = ('niri', 'xfce')


def desktop_profile():
    current = os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
    for profile in PROFILES:
        if profile in current:
            return profile
    try:
        profile = pathlib.Path('/etc/kestrel/desktop').read_text().strip()
        if profile in PROFILES:
            return profile
    except OSError:
        pass
    return 'xfce'


def load_content(directory=DATA):
    directory = pathlib.Path(directory)
    def read(name):
        return json.loads((directory/name).read_text(encoding='utf-8'))
    brand, center, shortcuts = read('branding.json'), read('control-center.json'), read('shortcuts.json')
    if not isinstance(brand, dict) or not isinstance(center, dict) or not isinstance(shortcuts, list):
        raise ValueError('Branding and Control Center must be JSON objects; shortcuts must be an array')
    for key in ('product_name', 'desktop_name', 'control_center_title', 'eyebrow', 'headline', 'subtitle', 'welcome_intro'):
        if not isinstance(brand.get(key), str) or not brand[key].strip():
            raise ValueError(f'branding.json: {key} must be nonempty text')
    if type(center.get('columns')) is not int or not 1 <= center['columns'] <= 4:
        raise ValueError('control-center.json: columns must be an integer from 1 to 4')
    if not isinstance(center.get('power_label'), str) or not center['power_label']:
        raise ValueError('control-center.json: power_label is required')
    if not isinstance(center.get('desktop_guides'), dict):
        raise ValueError('control-center.json: desktop_guides must be an object')
    for profile in PROFILES:
        if not isinstance(center['desktop_guides'].get(profile), str) or not center['desktop_guides'][profile].strip():
            raise ValueError(f'control-center.json: missing desktop guide for {profile}')
    identities = set()
    if not isinstance(center.get('actions'), list):
        raise ValueError('control-center.json: actions must be an array')
    for action in center['actions']:
        if not isinstance(action, dict):
            raise ValueError('control-center.json: each action must be an object')
        for key in ('id', 'label', 'icon'):
            if not isinstance(action.get(key), str) or not action[key]:
                raise ValueError(f'control-center.json: each action needs {key}')
        if action['id'] in identities:
            raise ValueError('control-center.json: duplicate action id '+action['id'])
        identities.add(action['id'])
        command = action.get('command')
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError('control-center.json: commands must be nonempty argument arrays')
        if 'enabled' in action and type(action['enabled']) is not bool:
            raise ValueError('control-center.json: enabled must be true or false')
        validate_profiles(action)
    for shortcut in shortcuts:
        if not isinstance(shortcut, dict):
            raise ValueError('shortcuts.json: each shortcut must be an object')
        for key in ('keys', 'label', 'binding'):
            if not isinstance(shortcut.get(key), str) or not shortcut[key]:
                raise ValueError(f'shortcuts.json: missing {key}')
        validate_profiles(shortcut)
    return brand, center, shortcuts


def validate_profiles(item):
    profiles = item.get('profiles', list(PROFILES))
    if not isinstance(profiles, list) or not profiles or any(profile not in PROFILES for profile in profiles):
        raise ValueError('profiles must contain niri and/or xfce')


def for_profile(items, profile):
    if profile not in PROFILES:
        raise ValueError('Unknown desktop profile: '+profile)
    return [item for item in items if item.get('enabled', True) and profile in item.get('profiles', PROFILES)]


def shortcut_text(shortcuts, profile, compact=False):
    return ('   ·   ' if compact else '\n').join(
        f"{item['keys']} · {item['label']}" for item in for_profile(shortcuts, profile)
        if not compact or item.get('compact'))

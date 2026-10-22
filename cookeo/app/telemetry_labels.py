"""Display labels only; raw protocol codes remain available for automations."""
PHASES = {
    'idle': ('Standby', 'Standby'),
    'menu': ('V nabídce', 'In menu'),
    'ready': ('Připraveno', 'Ready'),
    'warming': ('Zahřívání', 'Warming up'),
    'cooking': ('Probíhá vaření', 'Cooking'),
    'keep_warm': ('Udržování teploty', 'Keeping warm'),
    'depressurization': ('Uvolňování tlaku', 'Depressurizing'),
    'paused': ('Pozastaveno', 'Paused'),
    'done': ('Hotovo', 'Done'),
    'delayed': ('Odložený start', 'Delayed start'),
    'alert': ('Upozornění', 'Alert'),
    'off': ('Vypnuto', 'Off'),
}
MODES = {
    'manual': ('Ruční', 'Manual'),
    'program': ('Program', 'Program'),
    'recipe': ('Recept', 'Recipe'),
    'ingredient_cooking': ('Vaření surovin', 'Ingredient cooking'),
}


def telemetry_label(code, labels, language='en'):
    if code is None:
        return None
    normalized = code.strip().lower().replace(' ', '_').replace('-', '_')
    names = labels.get(normalized)
    return names[0 if language == 'cs' else 1] if names else code

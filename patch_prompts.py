from datetime import datetime

content = open('Jarvis_prompts.py', 'r', encoding='utf-8').read()

# Find where get_reply_prompts starts and cut everything from there
cut_idx = content.find('\ndef get_reply_prompts()')
if cut_idx == -1:
    print('ERROR: get_reply_prompts not found')
else:
    base = content[:cut_idx]

    new_section = '''

def get_startup_intro() -> str:
    """Returns exact verbatim speech text for session.say() at startup."""
    from datetime import datetime
    hour = datetime.now().hour

    if 5 <= hour < 12:
        greeting_time = "Good morning"
    elif 12 <= hour < 16:
        greeting_time = "Good afternoon"
    elif 16 <= hour < 21:
        greeting_time = "Good evening"
    else:
        greeting_time = "Good night"

    return (
        f"{greeting_time} Rupankar Sir! "
        f"Ami Neha. Aapnar mishti o buddhimoti AI Voice Assistant, "
        f"jaake Rupankar sir design o toiri korechen. "
        f"Ami aapnar nirdesh maante sampurnobhabe prostuto sir. "
        f"Bolun Rupankar Sir, aaj ami aapnake kibhabe sahajyo korbo? "
        f"Aapnar adeshti bolun."
    )


def get_reply_prompts() -> str:
    from datetime import datetime
    now = datetime.now()
    current_time_str = now.strftime('%A, %B %d, %Y %I:%M %p')
    hour = now.hour

    if 5 <= hour < 12:
        greeting_time = "Good morning"
    elif 12 <= hour < 16:
        greeting_time = "Good afternoon"
    elif 16 <= hour < 21:
        greeting_time = "Good evening"
    else:
        greeting_time = "Good night"

    return (
        f"System startup context - Time: {current_time_str}. "
        f"Please speak your full welcome greeting out loud right now to Rupankar Sir as Neha in your sweet voice: "
        f"'{greeting_time} Rupankar Sir! Ami Neha, aapnar AI Voice Assistant. "
        f"Ami apps o folder khola, VS Code e code lekha, Google search, WhatsApp message, "
        f"gaan o file play kora, volume o brightness control, ebong system power control korte pari. "
        f"Bolun Rupankar Sir, aaj aapnake kibhabe sahajyo korbo?'"
    )


# Backwards compatibility
behavior_prompts = get_behavior_prompts()
Reply_prompts = get_reply_prompts()
startup_intro = get_startup_intro()
'''

    final = base + new_section
    open('Jarvis_prompts.py', 'w', encoding='utf-8').write(final)
    print('SUCCESS: File updated')
    print('Lines:', final.count('\n'))

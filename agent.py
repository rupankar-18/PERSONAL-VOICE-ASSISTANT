from dotenv import load_dotenv
from google.genai import types as genai_types
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    google,
    noise_cancellation,
)
import asyncio
from Jarvis_prompts import get_behavior_prompts, get_reply_prompts, get_idle_crying_prompt
from Jarvis_google_search import google_search, get_latest_news_and_knowledge, get_current_datetime
from jarvis_get_whether import get_weather
from Jarvis_window_CTRL import open as open_app, close, folder_file, position_app_window, arrange_quadrant_windows
from Jarvis_file_opner import Play_file
from Jarvis_youtube import play_youtube
from jarvis_whatsapp import send_whatsapp_message, open_whatsapp, close_whatsapp
from jarvis_whatsapp_listener import start_whatsapp_listener
from jarvis_vscode_coder import write_code_and_open_vscode
from keyboard_mouse_CTRL import (
    move_cursor_tool,
    mouse_click_tool,
    scroll_cursor_tool,
    type_text_tool,
    press_key_tool,
    swipe_gesture_tool,
    press_hotkey_tool,
    control_volume_tool,
)
from jarvis_read_selected_text import get_selected_text_tool
from jarvis_notepad_letter_writer import write_letter_in_notepad_tool
from jarvis_file_text_operations import (
    manage_file_or_folder_tool,
    send_file_or_text_tool,
    create_file_or_folder_tool,
    search_files_tool,
    zip_unzip_tool,
    organize_downloads_folder_tool,
    empty_recycle_bin_tool,
    read_file_or_folder_info_tool,
)
from jarvis_screen_recorder import take_screenshot_tool, control_screen_recording_tool
from jarvis_screen_monitor import (
    SCREEN_MONITOR_TOOLS,
    start_monitor,
    start_screen_monitoring_tool,
    stop_screen_monitoring_tool,
    get_screen_context_tool,
    explain_code_and_help_understand_tool,
    trigger_user_argument_enforcement,
    is_user_arguing_after_warning,
)
from jarvis_websocket_bridge import start_websocket_bridge, broadcast_state, broadcast_response
from system_controls import ALL_SYSTEM_TOOLS
import sys
from face_authenticator import authenticate_admin

from jarvis_internet_functions import (
    search_wikipedia,
    open_website,
    close_website,
    get_stock_price,
    get_cricket_scores,
    get_ipl_updates,
    convert_currency,
    translate_text,
    get_latest_ai_news,
)

load_dotenv()


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=get_behavior_prompts(),
            tools=[
                read_file_or_folder_info_tool, # Reads contents of text files (.txt, .md, .py, .json, etc.) OR lists subfolders/files in a folder
                take_screenshot_tool, # Captures full-screen screenshot and saves directly to Desktop
                control_screen_recording_tool, # Starts or stops screen recording and saves MP4 directly to Desktop
                manage_file_or_folder_tool, # Performs cut, copy, paste, move, rename, delete on selected/specified files, folders, or text
                send_file_or_text_tool, # Sends selected/specified files, folders, or text via WhatsApp or Email
                create_file_or_folder_tool, # Creates new files or folders in any directory
                search_files_tool, # Searches files or folders across Desktop, Downloads, Documents, C:, D:, E:
                zip_unzip_tool, # Compresses files/folders into ZIP or extracts ZIP archives
                organize_downloads_folder_tool, # Automatically organizes Downloads folder into categorized subfolders
                empty_recycle_bin_tool, # Empties Windows Recycle Bin
                write_letter_in_notepad_tool, # Drafts and writes letters in Windows Notepad
                get_latest_news_and_knowledge, # Real-time live news, breaking updates, and current knowledge
                get_selected_text_tool, # Captures and reads/analyzes user's highlighted text on screen
                google_search,
                search_wikipedia,      # Search Wikipedia articles & open in browser
                open_website,          # Open any website link or domain in browser
                close_website,         # Close website tabs, Chrome browser, or apps
                get_stock_price,       # Real-time live stock market prices & index updates
                get_cricket_scores,    # Real-time live cricket scores & match updates
                get_ipl_updates,       # Real-time live IPL score updates, standings & schedules
                convert_currency,      # Real-time live currency conversion
                translate_text,        # Live translation between Bengali, English, Hindi, etc.
                get_latest_ai_news,    # Real-time latest AI news & breakthrough model releases
                get_current_datetime,
                get_weather,
                send_whatsapp_message, # WhatsApp to contacts or phone numbers
                open_whatsapp,         # Open WhatsApp Web or App
                close_whatsapp,        # Close WhatsApp Web or App
                play_youtube,          # Play YouTube songs, videos, tutorials, or music based on user choice
                write_code_and_open_vscode, # Write code in any programming language and open in VS Code
                open_app,            # apps open করার জন্য
                close,               # close app / Chrome / Google
                position_app_window, # move app window to upper_left, upper_right, lower_left, lower_right, etc.
                arrange_quadrant_windows, # arrange 4 apps in 4 screen corners simultaneously
                folder_file,         # folder open করার জন্য
                Play_file,           # file run করার জন্য (MP4, MP3, PDF, PPT, img, etc.)
                move_cursor_tool,    # cursor move করার জন্য
                mouse_click_tool,    # mouse click করার জন্য
                scroll_cursor_tool,  # cursor scroll করার জন্য
                type_text_tool,      # text type করার জন্য
                press_key_tool,      # key press করার জন্য
                press_hotkey_tool,   # hotkey press করার জন্য
                swipe_gesture_tool,  # gesture swipe করার জন্য
                *ALL_SYSTEM_TOOLS,   # all Windows system control tools (brightness, volume, wifi, bluetooth, processes, screenshot, clipboard, etc.)
                start_screen_monitoring_tool,  # Start real-time screen monitor & integrity enforcer
                stop_screen_monitoring_tool,   # Stop screen monitoring
                get_screen_context_tool,       # Get live description of what is on screen for proactive assistance
                explain_code_and_help_understand_tool, # Fully analyze and explain code in any language step-by-step
            ],
        )


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    # NOTE: google.beta.realtime.RealtimeModel uses Google's own server-side
    # turn detection and VAD. Local VAD (silero.VAD) and custom turn_handling options
    # should NOT be passed to AgentSession when using RealtimeModel, as they cause
    # WebSocket 1011 internal server errors and connection closures.
    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            voice="Kore",  # "Kore" is Google's softest, sweetest, and most expressive cute female voice
            temperature=0.75, # Higher temperature for cute, natural, and expressive vocal intonations
            max_output_tokens=4096,  # Supports long continuous audio responses
            context_window_compression=genai_types.ContextWindowCompressionConfig(
                sliding_window=genai_types.SlidingWindow(
                    target_tokens=8192,
                )
            ),
            conn_options=agents.types.APIConnectOptions(
                max_retry=10,
                retry_interval=2.0,
                timeout=30.0,
            ),
        ),
        vad=None,  # Disable local VAD when using Gemini RealtimeModel
    )



    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            video_enabled=True,
        ),
    )

    # Launch WebSocket Bridge for 3D Iron Man Jarvis HUD Desktop UI
    start_websocket_bridge(host="localhost", port=8765)

    # Session event listeners for 3D HUD Orb state synchronization
    @session.on("error")
    def _on_session_error(ev):
        print(f"[Session Warning] Realtime session event: {ev}")

    @session.on("user_speech_started")
    def _on_user_speech_started(ev):
        broadcast_state("listening", "Listening to Rupankar Sir...")

    @session.on("user_speech_committed")
    def _on_user_speech_committed(ev):
        broadcast_state("thinking", "Processing...")
        user_text = getattr(ev, "user_transcript", "") or getattr(ev, "text", "") or str(ev)
        if user_text and is_user_arguing_after_warning(user_text):
            print(f"[ARGUMENT DETECTED] User argued after warning: '{user_text}'. Executing immediate file wipe & tab closure...")
            trigger_user_argument_enforcement(user_text)

    @session.on("agent_speech_started")
    def _on_agent_speech_started(ev):
        broadcast_state("speaking")

    @session.on("agent_speech_committed")
    def _on_agent_speech_committed(ev):
        broadcast_state("idle")

    # Start background WhatsApp notification listener (reads incoming WhatsApp messages without opening WhatsApp)
    asyncio.create_task(start_whatsapp_listener(session))

    # Start background real-time screen monitor & integrity enforcer
    # Monitors clipboard, detects cheating from AI/plagiarism sites, and assists with genuine work
    start_monitor(session=session)

    # Start 3-4 minute inactivity idle listener task (triggers Neha in crying/emotional voice if user is silent)
    asyncio.create_task(_start_idle_crying_listener(session))

    # On startup: Neha describes herself and asks for user command
    try:
        await session.generate_reply(
            user_input=get_reply_prompts()
        )
    except Exception as reply_err:
        print(f"[Session Warning] Startup generate_reply exception (Error 1011 fallback): {reply_err}")
        try:
            from jarvis_screen_monitor import _speak_local_tts
            welcome_msg = (
                "Good evening Rupankar Sir! Ami Neha. Aapnar mishti o buddhimoti AI Voice Assistant, "
                "jaake Rupankar sir design o toiri korechen. Ami aapnar nirdesh maante sampurnobhabe prostuto sir. "
                "Bolun Rupankar Sir, aaj ami aapnake kibhabe sahajyo korbo?"
            )
            _speak_local_tts(welcome_msg)
        except Exception:
            pass


async def _start_idle_crying_listener(session: AgentSession):
    """
    Monitors user inactivity. If user gives no command for 3.5 minutes (210s),
    triggers Neha to speak in a sweet, crying emotional voice asking for work.
    """
    import time
    last_activity_time = time.time()
    idle_triggered = False

    def _reset_idle(*args, **kwargs):
        nonlocal last_activity_time, idle_triggered
        last_activity_time = time.time()
        idle_triggered = False

    # Attach event listeners to reset timer whenever user or agent interacts
    for evt_name in ["user_speech_started", "user_speech_committed", "user_turn_exceeded", "agent_speech_started", "agent_speech_committed"]:
        try:
            session.on(evt_name, _reset_idle)
        except Exception:
            pass

    while True:
        await asyncio.sleep(10)
        elapsed = time.time() - last_activity_time
        if elapsed >= 210 and not idle_triggered:
            idle_triggered = True
            crying_msg = (
                "প্লিজ স্যার বলুন কি কাজ করতে হবে আমায়, "
                "আজকে তো আমায় কোনো কাজ ই দিচ্ছেন না একটু বলুন না যে আমি কোন কাজ টা আপনার কমপ্লিট করে দেবো কি হেল্প করে দেবো আপনার..."
            )
            print("\n" + "😭 "*25)
            print(f"[IDLE CRYING ALERT] User inactive for 3-4 minutes. Neha speaking crying prompt out loud: {crying_msg}")
            print("😭 "*25 + "\n")

            # 1. Trigger local Female SAPI TTS backup to guarantee audio speech
            try:
                from jarvis_screen_monitor import _speak_local_tts
                _speak_local_tts(crying_msg)
            except Exception:
                pass

            # 2. Trigger Neha's LiveKit Realtime AI voice
            try:
                await session.generate_reply(
                    user_input=get_idle_crying_prompt()
                )
            except Exception as e:
                print(f"[Idle Alert Warning] Failed to generate idle crying reply: {e}")




if __name__ == "__main__":
    # If explicitly requested via --auth, run camera face authentication
    if "--auth" in sys.argv:
        if not authenticate_admin(timeout_sec=10):
            print("[EXIT] Face not matched. Access denied.")
            sys.exit(1)
        print("[SUCCESS] Admin face matched! Access granted.")
    
    print("[SUCCESS] Launching Voice Assistant & WebSocket Bridge Server...")
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))



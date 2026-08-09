import asyncio
import logging
from typing import Set, Tuple, List

logger = logging.getLogger(__name__)

# Try importing WinRT notification modules
try:
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )
    from winrt.windows.ui.notifications import (
        NotificationKinds,
        KnownNotificationBindings,
    )
    import winrt.windows.applicationmodel
    WINRT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WinRT notification listener modules could not be imported: {e}")
    WINRT_AVAILABLE = False


def _extract_sender_and_message(lines: List[str]) -> Tuple[str, str]:
    """
    Extracts sender name and message body from toast text lines.
    Handles various notification layouts from WhatsApp Desktop, Web, and UWP apps.
    """
    if not lines:
        return "Someone", "New message received."

    # Filter out pure app name header lines if present at index 0
    filtered = [l for l in lines if l.lower() not in ("whatsapp", "whatsapp web", "whatsapp desktop", "whatsapp beta")]
    if not filtered:
        filtered = lines

    if len(filtered) == 1:
        text = filtered[0]
        if ":" in text:
            parts = text.split(":", 1)
            sender = parts[0].strip()
            msg = parts[1].strip()
            return sender if sender else "Someone", msg if msg else "New message received."
        else:
            return text, "New message received."

    # If filtered has 2 or more text elements
    sender = filtered[0].strip()
    msg = " ".join(filtered[1:]).strip()

    # Check if sender line itself has "Name: message" format
    if ":" in sender:
        parts = sender.split(":", 1)
        sender = parts[0].strip()
        msg = f"{parts[1].strip()} {msg}".strip()

    return sender if sender else "Someone", msg if msg else "New message received."


async def start_whatsapp_listener(session, poll_interval: float = 1.0):
    """
    Background worker that polls Windows Action Center toast notifications for WhatsApp incoming messages.
    When a new WhatsApp notification arrives, it extracts sender name & message content,
    prints a clear alert to the console, and asks Neha (AgentSession) to announce it out loud to the admin.
    """
    if not WINRT_AVAILABLE:
        logger.warning("[WhatsApp Listener] WinRT notification modules not available. WhatsApp listener disabled.")
        return

    try:
        listener = UserNotificationListener.current
        status = await listener.request_access_async()

        if status != UserNotificationListenerAccessStatus.ALLOWED:
            logger.warning(f"[WhatsApp Listener] Access to Windows notifications denied (status: {status}).")
            return

        logger.info("[WhatsApp Listener] Listener started successfully. Monitoring incoming WhatsApp messages...")

        seen_notification_ids: Set[int] = set()

        # Seed existing notifications so old notifications are not re-announced on startup
        try:
            initial_notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
            for notif in initial_notifs:
                seen_notification_ids.add(notif.id)
            logger.info(f"[WhatsApp Listener] Initialized with {len(seen_notification_ids)} existing notifications.")
        except Exception as e:
            logger.warning(f"[WhatsApp Listener] Failed to fetch initial notifications: {e}")

        while True:
            try:
                current_notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
                for notif in current_notifs:
                    if notif.id in seen_notification_ids:
                        continue

                    seen_notification_ids.add(notif.id)

                    app_name = ""
                    app_id = ""
                    try:
                        if hasattr(notif, "app_info") and notif.app_info:
                            app_info = notif.app_info
                            if hasattr(app_info, "display_info") and app_info.display_info:
                                app_name = app_info.display_info.display_name or ""
                            if hasattr(app_info, "app_user_model_id") and app_info.app_user_model_id:
                                app_id = app_info.app_user_model_id or ""
                            elif hasattr(app_info, "id") and app_info.id:
                                app_id = app_info.id or ""
                    except Exception as e:
                        logger.debug(f"[WhatsApp Listener] App info retrieval exception: {e}")

                    # Get notification text lines
                    lines: List[str] = []
                    try:
                        visual = notif.notification.visual
                        binding = visual.get_binding(KnownNotificationBindings.toast_generic) if hasattr(KnownNotificationBindings, "toast_generic") else visual.get_binding("ToastGeneric")
                        if binding:
                            text_elements = binding.get_text_elements()
                            lines = [elem.text.strip() for elem in text_elements if elem.text and elem.text.strip()]
                    except Exception as visual_err:
                        logger.debug(f"[WhatsApp Listener] Visual text extraction error: {visual_err}")

                    # Determine if this notification is from WhatsApp
                    is_whatsapp = (
                        "whatsapp" in app_name.lower()
                        or "whatsapp" in app_id.lower()
                        or any("whatsapp" in line.lower() for line in lines)
                    )

                    if is_whatsapp:
                        sender_name, message_text = _extract_sender_and_message(lines)

                        print(f"\n==================================================")
                        print(f"  [🔔 INCOMING WHATSAPP MESSAGE RECEIVED]")
                        print(f"  From: {sender_name}")
                        print(f"  Message: {message_text}")
                        print(f"==================================================\n")

                        logger.info(f"[WhatsApp Listener] New message from '{sender_name}': {message_text}")

                        # Construct system notification prompt for Neha to announce out loud
                        announcement_prompt = (
                            f"[SYSTEM ALERT - INCOMING WHATSAPP MESSAGE]\n"
                            f"Sender: {sender_name}\n"
                            f"Message: {message_text}\n"
                            f"Instruction: Rupankar Sir, announce out loud to the admin immediately as Neha in your sweet voice: "
                            f"'Rupankar Sir! {sender_name} WhatsApp-e ekta message pathiyechen: {message_text}'."
                        )

                        if session:
                            try:
                                await session.generate_reply(user_input=announcement_prompt)
                            except Exception as session_err:
                                logger.error(f"[WhatsApp Listener] Error generating voice reply: {session_err}")

            except Exception as loop_err:
                logger.error(f"[WhatsApp Listener] Error polling notifications: {loop_err}")

            await asyncio.sleep(poll_interval)

    except asyncio.CancelledError:
        logger.info("[WhatsApp Listener] Notification listener task cancelled.")
    except Exception as e:
        logger.error(f"[WhatsApp Listener] Fatal error in notification listener: {e}", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print("==========================================================")
    print("  [WHATSAPP LISTENER STANDALONE TEST MODE]")
    print("  Monitoring Windows Action Center for WhatsApp messages...")
    print("  Press Ctrl+C to stop.")
    print("==========================================================")
    try:
        asyncio.run(start_whatsapp_listener(session=None, poll_interval=1.0))
    except KeyboardInterrupt:
        print("\n[STOPPED] WhatsApp Listener stopped by user.")


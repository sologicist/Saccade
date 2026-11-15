// User container — the user's message for this run, top right of the main
// grid like a chat, the first zone of the live turn (#liveTurn, index.tsx).
// Empty and hidden until a message is sent (user.js fills it:
// window.showUserMessage). This was user.html, injected by user.js.
import { Avatar } from '../../components/ui/agent-avatar';

export function UserContainer() {
    return (
        <div className="container-zone user-container is-empty" id="userContainer" aria-label="Your message">
            <div className="user-message-avatar"><Avatar name="You" size="sm" kind="person" /></div>
            <div className="user-message-body">
                <div className="user-message-meta">
                    <span className="user-message-name">You</span>
                    <time className="user-message-time" hidden />
                </div>
                {/* Where the message came from, when not this chat box. */}
                <div className="user-message-via" id="userMessageVia" hidden></div>
                <div className="user-message-text" id="userMessageText"></div>
            </div>
        </div>
    );
}

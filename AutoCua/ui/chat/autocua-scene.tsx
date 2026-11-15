import type { CSSProperties } from 'react';
import { UserContainer } from '../container/user/user.tsx';
import { ScreenContainer } from '../container/screen/screen.tsx';
import { AgentContainer } from '../container/agent/agent.tsx';
import { ChatInput } from '../chat_input/chat_input.tsx';

// Keep AutoCua's original DOM targets and controllers together. React only
// adjusts the available space; the native runtime owns the scene and its turns.
export function AutoCuaScene({ bottomInset }: { bottomInset: number }) {
  return <div className="autocua-scene" style={{ '--composer-inset': `${bottomInset}px` } as CSSProperties}>
    <div className="welcome-hero" id="welcomeHero" aria-hidden="true">
      <div className="welcome-bloub">
        <div className="bot" role="img" aria-label="AutoCua">
          <img src="bots/autocua.webp" alt="" />
          <img src="bots/autocua-eyes.webp" alt="" />
          <img src="bots/autocua-shine.webp" alt="" />
        </div>
      </div>
      <div className="welcome-hero-title">Made to do...</div>
    </div>
    <div className="main-grid" id="mainGrid">
      <div className="chat-scroll" id="chatScroll">
        <div className="chat-past" id="chatPast" />
        <div className="chat-turn live" id="liveTurn">
          <UserContainer />
          <ScreenContainer />
          <AgentContainer />
        </div>
      </div>
    </div>
    {/* Keep the native input as the agent controller and the bot's geometry
        anchor. TUFFUI provides the visible composer and its controls. */}
    <div className="chat-container-wrapper" id="chatWrapper" aria-hidden="true"><ChatInput /></div>
  </div>;
}

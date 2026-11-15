"use client";

import { ArrowDown, Sparkle } from "@phosphor-icons/react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { Panel, Shell } from "@/components/ui/surface";
import { enter, exit } from "@/lib/motion-tokens";
import { cn } from "@/lib/utils";
import { Avatar } from "@/components/ui/agent-avatar";

export type ThreadMessage = {
  id: string;
  role: "user" | "assistant";
  content: React.ReactNode;
  /** ISO timestamp; drives grouping, date dividers and the hover time. */
  at: string;
  /** Name shown at the start of a group; defaults to `userName` / `agentName`. */
  author?: string;
  streaming?: boolean;
};

export type ChatThreadProps = {
  data: { messages: ThreadMessage[]; unreadFrom?: string };
  density?: "default" | "dense";
  agentName?: string;
  userName?: string;
  /** Custom avatar per role; defaults to a sparkle for the agent and initials for people. */
  renderAvatar?: (message: ThreadMessage) => React.ReactNode;
  /** Height of the scroll area. */
  height?: number | string;
  /**
   * No shell or panel: the thread is just the scroll area and fills its parent
   * (`height` defaults to 100%). For full screens where the thread is the page.
   */
  bare?: boolean;
  /** Rendered after the last message, inside the scroll area (e.g. follow-up chips). */
  footer?: React.ReactNode;
  /** Space kept free at the bottom, in px, for a composer that floats over the thread. */
  bottomInset?: number;
  /** Classes for the message column, e.g. `mx-auto max-w-3xl` to centre it. */
  contentClassName?: string;
  className?: string;
};

/** Turns from the same side within this window share one header. */
const GROUP_MS = 5 * 60_000;
/** How close to the bottom still counts as "following" the conversation. */
const STICK_PX = 48;

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

function dayLabel(iso: string) {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString("en-US", { month: "long", day: "numeric" });
}

// Day boundaries depend on the viewer's time zone, which prerendered HTML can't
// know: until hydration they're computed in UTC so both renders agree.
const noop = () => () => {};
const useHydrated = () =>
  useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );

export function ChatThread({
  data,
  density = "default",
  agentName = "Assistant",
  userName = "You",
  renderAvatar,
  height,
  bare = false,
  footer,
  bottomInset = 0,
  contentClassName,
  className,
}: ChatThreadProps) {
  const hydrated = useHydrated();
  const dayKey = (iso: string) =>
    hydrated ? new Date(iso).toDateString() : iso.slice(0, 10);
  const { messages, unreadFrom } = data;
  const dense = density === "dense";
  const reduce = useReducedMotion();
  const scroller = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const [away, setAway] = useState(false);
  // Message count when the reader scrolled away; anything after is "new".
  const [seen, setSeen] = useState(messages.length);
  const fresh = away ? Math.max(messages.length - seen, 0) : 0;
  const streaming = messages.some((m) => m.streaming);

  const toBottom = (smooth: boolean) => {
    const el = scroller.current;
    if (el)
      el.scrollTo({
        top: el.scrollHeight,
        behavior: smooth && !reduce ? "smooth" : "auto",
      });
  };

  // Stick to the bottom while following, including as a streamed answer grows.
  useLayoutEffect(() => {
    if (following.current) toBottom(false);
  });
  useEffect(() => {
    const node = content.current;
    if (!node) return;
    const observer = new ResizeObserver(() => following.current && toBottom(false));
    observer.observe(node);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
    following.current = atBottom;
    if (atBottom !== !away) {
      setAway(!atBottom);
      if (!atBottom) setSeen(messages.length);
    }
  };

  const avatar = (message: ThreadMessage) =>
    renderAvatar?.(message) ??
    (message.role === "assistant" ? (
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-full bg-brand/15 text-brand"
      >
        <Sparkle weight="fill" className="size-3.5" />
      </span>
    ) : (
      <Avatar name={message.author ?? userName} size="sm" kind="person" />
    ));

  return (
    <MotionConfig reducedMotion="user">
      <Frame bare={bare} className={className}>
        <div
          ref={scroller}
          onScroll={onScroll}
          role="log"
          aria-label="Conversation"
          aria-busy={streaming || undefined}
          tabIndex={0}
          className="overflow-x-hidden overflow-y-auto overscroll-contain outline-none"
          style={{ height: height ?? (bare ? "100%" : 420) }}
        >
          <div
            ref={content}
            className={cn(
              "flex flex-col",
              dense ? "gap-1 p-3" : "gap-1.5 px-4 py-5",
              contentClassName,
            )}
            style={bottomInset ? { paddingBottom: bottomInset + 20 } : undefined}
          >
            <AnimatePresence initial={false}>
              {messages.map((message, i) => {
                const prev = messages[i - 1];
                const newDay = !prev || dayKey(prev.at) !== dayKey(message.at);
                const grouped =
                  !newDay &&
                  prev?.role === message.role &&
                  new Date(message.at).getTime() - new Date(prev.at).getTime() <
                    GROUP_MS &&
                  message.id !== unreadFrom;
                const user = message.role === "user";
                const name = message.author ?? (user ? userName : agentName);

                return (
                  <Fragment key={message.id}>
                    {newDay && <Divider label={dayLabel(message.at)} />}
                    {message.id === unreadFrom && <Divider label="Unread" tone="brand" />}
                    <motion.article
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0, transition: enter }}
                      exit={{ opacity: 0, transition: exit }}
                      aria-label={`${name}, ${time(message.at)}`}
                      // Times are formatted in the viewer's time zone, which can differ from the server's.
                      suppressHydrationWarning
                      className={cn(
                        "group flex gap-2.5",
                        user && "flex-row-reverse",
                        !grouped && i > 0 && (dense ? "mt-2" : "mt-4"),
                      )}
                    >
                      {!dense &&
                        (grouped ? (
                          <span aria-hidden="true" className="w-7 shrink-0" />
                        ) : (
                          avatar(message)
                        ))}
                      <div
                        className={cn(
                          "flex min-w-0 flex-col gap-1",
                          // Assistant turns stretch so rich content (cards, carousels) gets the
                          // full column instead of the width of the text beside it.
                          user ? "items-end" : "items-stretch",
                          user ? "max-w-[80%]" : "max-w-[92%] flex-1",
                        )}
                      >
                        {!grouped && (
                          <p
                            className={cn(
                              "flex items-baseline gap-2 text-[0.8125rem]",
                              user && "flex-row-reverse",
                            )}
                          >
                            <span className="font-medium">{name}</span>
                            <time
                              dateTime={message.at}
                              suppressHydrationWarning
                              className="text-xs text-muted-foreground tabular-nums opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                            >
                              {time(message.at)}
                            </time>
                          </p>
                        )}
                        <div
                          className={cn(
                            // max-w-full keeps rich content (tool calls, source lists) inside the column.
                            "max-w-full text-sm leading-relaxed",
                            user &&
                              "rounded-2xl bg-surface-raised px-3.5 py-2 whitespace-pre-wrap",
                            user && !grouped && "rounded-tr-md",
                          )}
                        >
                          {message.content}
                          {message.streaming && (
                            <span
                              aria-hidden="true"
                              className="ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] animate-pulse rounded-full bg-brand motion-reduce:animate-none"
                            />
                          )}
                        </div>
                      </div>
                    </motion.article>
                  </Fragment>
                );
              })}
            </AnimatePresence>
            {footer}
          </div>
        </div>

        <AnimatePresence>
          {away && (
            <motion.button
              type="button"
              onClick={() => {
                following.current = true;
                setAway(false);
                toBottom(true);
              }}
              initial={{ opacity: 0, y: 8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1, transition: enter }}
              exit={{ opacity: 0, y: 4, transition: exit }}
              style={{ bottom: bottomInset + 12 }}
              className="absolute left-1/2 flex h-8 -translate-x-1/2 items-center gap-1.5 rounded-full bg-surface-raised px-3.5 text-[0.8125rem] font-medium transition-[background-color,scale] duration-150 ease-out hover:bg-[color-mix(in_oklab,var(--surface-raised),var(--foreground)_7%)] active:scale-[0.97]"
            >
              <ArrowDown weight="bold" className="size-3.5" aria-hidden="true" />
              Jump to latest
              {fresh > 0 && (
                <span className="text-muted-foreground tabular-nums">· {fresh} new</span>
              )}
            </motion.button>
          )}
        </AnimatePresence>
      </Frame>
    </MotionConfig>
  );
}

function Frame({
  bare,
  className,
  children,
}: {
  bare: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  if (bare)
    return <div className={cn("relative h-full w-full", className)}>{children}</div>;
  return (
    <Shell className={cn("w-full max-w-2xl", className)}>
      <Panel className="relative overflow-hidden">{children}</Panel>
    </Shell>
  );
}

function Divider({ label, tone }: { label: string; tone?: "brand" }) {
  // A centred pill instead of a hairline rule; the thread has no borders.
  return (
    <div
      role="separator"
      aria-label={label}
      suppressHydrationWarning
      className="my-3 flex justify-center"
    >
      <span
        suppressHydrationWarning
        className={cn(
          "rounded-full px-2.5 py-0.5 text-[0.6875rem] font-medium",
          tone === "brand"
            ? "bg-brand/15 text-brand"
            : "bg-foreground/[0.05] text-muted-foreground",
        )}
      >
        {label}
      </span>
    </div>
  );
}

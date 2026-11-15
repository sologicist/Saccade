"use client";

import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";

const sizes = {
  sm: "h-5 min-w-5 px-1 text-[0.6875rem] rounded-md",
  md: "h-6 min-w-6 px-1.5 text-xs rounded-lg",
} as const;

export type KbdProps = React.ComponentProps<"kbd"> & { size?: keyof typeof sizes };

/** One key as a small raised chip. */
export function Kbd({ size = "sm", className, ...props }: KbdProps) {
  return (
    <kbd
      className={cn(
        "inline-flex shrink-0 items-center justify-center bg-foreground/[0.08] font-sans font-medium text-muted-foreground tabular-nums",
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}

// Platform is read after mount: the server and first client render assume
// "other", so the markup always matches and Mac users see ⌘ a frame later.
const subscribe = () => () => {};
const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

/** True where the modifier key is ⌘, once mounted; false during prerender. */
export function useIsMac() {
  return useSyncExternalStore(subscribe, isMac, () => false);
}

const mac: Record<string, string> = {
  mod: "⌘",
  cmd: "⌘",
  ctrl: "⌃",
  alt: "⌥",
  option: "⌥",
  shift: "⇧",
};
const other: Record<string, string> = {
  mod: "Ctrl",
  cmd: "Ctrl",
  ctrl: "Ctrl",
  alt: "Alt",
  option: "Alt",
  shift: "Shift",
};
const common: Record<string, string> = {
  enter: "↵",
  return: "↵",
  esc: "Esc",
  escape: "Esc",
  up: "↑",
  down: "↓",
  left: "←",
  right: "→",
  tab: "Tab",
  space: "Space",
  backspace: "⌫",
};
const spoken: Record<string, string> = {
  "⌘": "Command",
  "⌃": "Control",
  "⌥": "Option",
  "⇧": "Shift",
  "↵": "Enter",
  "↑": "Up",
  "↓": "Down",
  "←": "Left",
  "→": "Right",
  "⌫": "Backspace",
};

/** Turns "mod+shift+k" into the keys for this platform. */
export function formatKeys(combo: string, onMac: boolean) {
  return combo
    .split("+")
    .map((k) => k.trim().toLowerCase())
    .filter(Boolean)
    .map((k) => (onMac ? mac : other)[k] ?? common[k] ?? k.toUpperCase());
}

export type KeyComboProps = Omit<React.ComponentProps<"span">, "children"> & {
  /** Keys joined by "+", e.g. "mod+k", "shift+enter". `mod` is ⌘ on Mac and Ctrl elsewhere. */
  keys: string;
  size?: keyof typeof sizes;
};

/** A shortcut as separate key chips, adapted to the viewer's platform. */
export function KeyCombo({ keys, size = "sm", className, ...props }: KeyComboProps) {
  const onMac = useIsMac();
  const parts = formatKeys(keys, onMac);
  return (
    <span
      className={cn("inline-flex items-center gap-0.5 align-middle", className)}
      {...props}
    >
      <span className="sr-only">{parts.map((p) => spoken[p] ?? p).join(" ")}</span>
      {parts.map((part, i) => (
        <Kbd key={i} size={size} aria-hidden="true">
          {part}
        </Kbd>
      ))}
    </span>
  );
}

"use client";

import { At, FileText, Paperclip, Repeat, X } from "@phosphor-icons/react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useId, useLayoutEffect, useRef, useState } from "react";
import { Button, IconButton } from "@/components/ui/action-button";
import { Segmented } from "@/components/ui/segmented-control";
import { Panel, Shell } from "@/components/ui/surface";
import { enter, exit as leave, spring as slide } from "@/lib/motion-tokens";
import { cn } from "@/lib/utils";
import { Kbd } from "@/components/ui/key-hint";
import { Spinner } from "@/components/ui/loader";

export type ComposerMode = "ask" | "plan" | "act";
export type ComposerContextItem = { id: string; name: string; tokens: number };
export type ComposerFile = { id: string; path: string; tokens: number };
export type ComposerModel = { id: string; name: string; description?: string };
export type ComposerCommand = { name: string; description: string };
export type ComposerQueued = { id: string; text: string };
export type ComposerMessage = {
  text: string;
  mode: ComposerMode;
  context: ComposerContextItem[];
  model?: string;
};

export type AgentComposerProps = {
  value?: string;
  onValueChange?: (value: string) => void;
  /** Hide the Ask / Plan / Act switch with `showModes={false}`. */
  mode?: ComposerMode;
  onModeChange?: (mode: ComposerMode) => void;
  showModes?: boolean;
  /** Files and attachments sent with the message, shown in the context tray. */
  context?: ComposerContextItem[];
  onContextChange?: (context: ComposerContextItem[]) => void;
  /** Candidates for the @ mention menu. */
  files?: ComposerFile[];
  commands?: ComposerCommand[];
  models?: ComposerModel[];
  model?: string;
  onModelChange?: (model: string) => void;
  status?: "idle" | "streaming";
  /** Messages sent while the agent works. Pop the next one when a run ends. */
  queue?: ComposerQueued[];
  onQueueChange?: (queue: ComposerQueued[]) => void;
  onSubmit?: (message: ComposerMessage) => void | boolean;
  onStop?: () => void;
  allowAttachments?: boolean;
  /** Runtime controls, using the same footer layout as the stock composer. */
  toolbar?: React.ReactNode;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
};

const modes: { id: ComposerMode; label: string; hint: string }[] = [
  { id: "ask", label: "Ask", hint: "Answers questions, changes nothing" },
  { id: "plan", label: "Plan", hint: "Drafts a plan for you to approve" },
  { id: "act", label: "Act", hint: "Can edit files and run commands" },
];

// Strong ease-out for things entering; exits are quicker than entrances.
const pop = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1, transition: enter },
  exit: { opacity: 0, scale: 0.95, transition: leave },
  // Neighbors reflow with `layout` when a chip comes or goes.
  transition: slide,
};
const fold = {
  initial: { height: 0, opacity: 0 },
  animate: { height: "auto", opacity: 1, transition: enter },
  exit: { height: 0, opacity: 0, transition: leave },
};

export const formatTokens = (n: number) =>
  n < 1000 ? `${n}` : `${(n / 1000).toFixed(n < 100_000 ? 1 : 0)}k`;

/** Controlled when `value` is passed, otherwise keeps its own state. */
function useControllable<T>(
  value: T | undefined,
  onChange: ((v: T) => void) | undefined,
  initial: T,
) {
  const [inner, setInner] = useState(initial);
  const set = (next: T) => {
    if (value === undefined) setInner(next);
    onChange?.(next);
  };
  return [value ?? inner, set] as const;
}

type MenuItem = { key: string; label: string; detail: string; run: () => void };

export function AgentComposer({
  value: valueProp,
  onValueChange,
  mode: modeProp,
  onModeChange,
  showModes = true,
  context: contextProp,
  onContextChange,
  files = [],
  commands = [],
  models = [],
  model: modelProp,
  onModelChange,
  status = "idle",
  queue: queueProp,
  onQueueChange,
  onSubmit,
  onStop,
  allowAttachments = true,
  toolbar,
  disabled = false,
  placeholder = "Describe the change, @ to add files, / for commands",
  className,
}: AgentComposerProps) {
  const id = useId();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const seq = useRef(0);
  const [value, setValue] = useControllable(valueProp, onValueChange, "");
  const [mode, setMode] = useControllable(modeProp, onModeChange, "act");
  const [context, setContext] = useControllable(contextProp, onContextChange, []);
  const [queue, setQueue] = useControllable(queueProp, onQueueChange, []);
  const [model, setModel] = useControllable(
    modelProp,
    onModelChange,
    models[0]?.id ?? "",
  );
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const streaming = status === "streaming";

  // One menu at a time: "/word" as the whole input, or "@word" at the end of it.
  const slash = /^\/(\S*)$/.exec(value)?.[1];
  const mention = /(?:^|\s)@(\S*)$/.exec(value)?.[1];
  const items: MenuItem[] =
    slash !== undefined
      ? commands
          .filter((c) => c.name.includes(slash.toLowerCase()))
          .map((c) => ({
            key: c.name,
            label: `/${c.name}`,
            detail: c.description,
            run: () => setValue(`/${c.name} `),
          }))
      : mention !== undefined
        ? files
            .filter(
              (f) =>
                f.path.toLowerCase().includes(mention.toLowerCase()) &&
                !context.some((c) => c.id === f.id),
            )
            .slice(0, 6)
            .map((f) => ({
              key: f.id,
              label: f.path,
              detail: `${formatTokens(f.tokens)} tokens`,
              run: () => {
                setValue(value.replace(/@\S*$/, ""));
                setContext([...context, { id: f.id, name: f.path, tokens: f.tokens }]);
              },
            }))
        : [];
  const menuOpen = items.length > 0 && dismissed !== value;
  const activeIndex = Math.min(active, items.length - 1);

  useLayoutEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const canSend = value.trim().length > 0;
  const submit = () => {
    if (disabled) return;
    if (!canSend) return;
    if (streaming)
      setQueue([...queue, { id: `${id}-q${++seq.current}`, text: value.trim() }]);
    else {
      if (onSubmit?.({ text: value.trim(), mode: showModes ? mode : "act", context, model }) === false) return;
      setContext([]);
    }
    setValue("");
  };
  const pick = (item: MenuItem) => {
    item.run();
    setActive(0);
    textarea.current?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen) {
      const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
      if (step) {
        event.preventDefault();
        setActive((activeIndex + step + items.length) % items.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        pick(items[activeIndex]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setDismissed(value);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  const total = context.reduce((n, c) => n + c.tokens, 0);
  const current = modes.find((m) => m.id === mode) ?? modes[2];
  const currentModel = models.find((m) => m.id === model);
  const showTray = allowAttachments || context.length > 0;

  return (
    <MotionConfig reducedMotion="user">
      <Shell className={cn("relative max-w-xl", className)}>
        {/* Opened by typing / or @, so it appears instantly: keyboard actions never animate. */}
        {menuOpen && (
          <ul
            id={`${id}-menu`}
            role="listbox"
            aria-label={slash !== undefined ? "Commands" : "Files"}
            className="absolute inset-x-0 bottom-full z-10 mb-2 rounded-[1.375rem] bg-surface-raised p-1.5"
          >
            {items.map((item, i) => (
              <li
                key={item.key}
                id={`${id}-opt-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(item)}
                onMouseMove={() => setActive(i)}
                className="flex cursor-pointer items-baseline gap-3 rounded-xl px-3 py-2 text-[0.8125rem] aria-selected:bg-foreground/[0.07]"
              >
                <span className="truncate font-mono">{item.label}</span>
                <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                  {item.detail}
                </span>
              </li>
            ))}
          </ul>
        )}
        {(showModes || models.length > 0) && (
          <div className="flex items-center gap-3 px-1 pt-0.5 pb-2">
            {showModes && (
              <Segmented
                label="Mode"
                className="h-7 shrink-0"
                options={modes.map((m) => ({ value: m.id, label: m.label }))}
                value={mode}
                onValueChange={setMode}
              />
            )}
            {showModes && (
              <motion.p
                key={current.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={enter}
                className="hidden min-w-0 truncate text-xs text-muted-foreground @md:block"
              >
                {current.hint}
              </motion.p>
            )}
            {currentModel && (
              <button
                type="button"
                title={`${currentModel.name}${currentModel.description ? ` — ${currentModel.description}` : ""}`}
                aria-label={`Model: ${currentModel.name}. Switch model`}
                onClick={() =>
                  setModel(models[(models.indexOf(currentModel) + 1) % models.length].id)
                }
                className="ml-auto flex shrink-0 items-center gap-1 rounded-md px-1.5 font-mono text-xs text-muted-foreground transition-[color,scale] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] hover:text-foreground active:scale-[0.97]"
              >
                {currentModel.id}
                <Repeat weight="fill" className="size-3" aria-hidden="true" />
              </button>
            )}
          </div>
        )}
        <AnimatePresence initial={false}>
          {queue.length > 0 && (
            <motion.div {...fold} className="overflow-hidden">
              <p className="px-2.5 pb-1 text-xs text-muted-foreground">
                Queued · {queue.length}
              </p>
              <ol aria-label="Queued messages" className="mb-1.5 space-y-1">
                <AnimatePresence initial={false}>
                  {queue.map((q) => (
                    <motion.li
                      key={q.id}
                      layout
                      {...pop}
                      className="flex items-center gap-2 rounded-xl bg-foreground/[0.04] py-1.5 pr-1 pl-3 text-[0.8125rem]"
                    >
                      <span className="min-w-0 flex-1 truncate">{q.text}</span>
                      <RemoveButton
                        label={`Remove queued message: ${q.text}`}
                        onClick={() => setQueue(queue.filter((x) => x.id !== q.id))}
                      />
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ol>
            </motion.div>
          )}
        </AnimatePresence>
        <Panel className="relative">
          {showTray && (
            <ul
              aria-label="Context"
              className="flex flex-wrap items-center gap-1.5 px-3 pt-3"
            >
              <AnimatePresence mode="popLayout" initial={false}>
                {context.map((c) => (
                  <motion.li
                    key={c.id}
                    layout
                    {...pop}
                    className="flex h-7 items-center gap-1.5 rounded-lg bg-foreground/[0.05] pr-0.5 pl-2 text-xs"
                  >
                    <FileText
                      weight="fill"
                      className="size-3.5 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <span className="max-w-44 truncate font-mono">{c.name}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {formatTokens(c.tokens)}
                    </span>
                    <RemoveButton
                      label={`Remove ${c.name}`}
                      onClick={() => setContext(context.filter((x) => x.id !== c.id))}
                    />
                  </motion.li>
                ))}
              </AnimatePresence>
              {allowAttachments && (
                <li>
                  <input
                    ref={fileInput}
                    type="file"
                    multiple
                    hidden
                    onChange={(event) => {
                      const added = Array.from(event.target.files ?? []).map((f) => ({
                        id: `${f.name}-${f.size}-${f.lastModified}`,
                        name: f.name,
                        tokens: Math.ceil(f.size / 4), // rough estimate: ~4 bytes per token
                      }));
                      setContext([...context, ...added]);
                      event.target.value = "";
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => fileInput.current?.click()}
                    className="flex h-7 items-center gap-1.5 rounded-lg px-2 text-xs text-muted-foreground transition-[color,background-color,scale] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] hover:bg-foreground/[0.05] hover:text-foreground active:scale-[0.97]"
                  >
                    <Paperclip weight="fill" className="size-3.5" aria-hidden="true" />
                    {context.length ? "Add" : "Add context"}
                  </button>
                </li>
              )}
              {total > 0 && (
                <li className="ml-auto font-mono text-xs text-muted-foreground tabular-nums">
                  + {formatTokens(total)} tokens
                </li>
              )}
            </ul>
          )}
          <label htmlFor={`${id}-input`} className="sr-only">
            Message
          </label>
          <textarea
            ref={textarea}
            id={`${id}-input`}
            rows={1}
            value={value}
            disabled={disabled}
            placeholder={
              streaming ? "Add a follow-up — it runs when the agent is done" : placeholder
            }
            onChange={(event) => {
              setValue(event.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={menuOpen}
            aria-controls={`${id}-menu`}
            aria-activedescendant={menuOpen ? `${id}-opt-${activeIndex}` : undefined}
            className="block max-h-[180px] min-h-16 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-sm leading-6 outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center gap-2 px-2 pb-2 pl-4">
            <div className="flex min-w-0 flex-1 items-center gap-1.5 text-xs text-muted-foreground">
              {toolbar ? toolbar : streaming ? (
                <>
                  <Spinner size="sm" label="Agent working" className="text-brand" />
                  Working · new messages queue
                </>
              ) : (
                <>
                  <At weight="fill" className="size-3 shrink-0" aria-hidden="true" />{" "}
                  files · / commands
                </>
              )}
            </div>
            {streaming && (
              <Button
                variant="quiet"
                onClick={onStop}
                className="px-3 text-negative hover:bg-negative/10 hover:text-negative"
              >
                Stop
              </Button>
            )}
            <Button
              variant={
                !streaming && (mode === "act" || !showModes) ? "primary" : "secondary"
              }
              disabled={disabled || !canSend}
              onClick={submit}
              className={cn(
                "gap-2",
                !streaming &&
                  mode !== "act" &&
                  showModes &&
                  "bg-foreground text-background hover:bg-foreground/90",
              )}
            >
              {streaming ? "Queue" : "Send"}
              <Kbd aria-hidden="true" className="bg-current/15 text-current opacity-80">
                ↵
              </Kbd>
            </Button>
          </div>
        </Panel>
        <p role="status" aria-live="polite" className="sr-only">
          {streaming
            ? `Agent is working${queue.length ? `, ${queue.length} queued` : ""}`
            : ""}
        </p>
      </Shell>
    </MotionConfig>
  );
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <IconButton
      icon={X}
      iconWeight="bold"
      label={label}
      onClick={onClick}
      className="size-6 rounded-md"
    />
  );
}

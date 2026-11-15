"use client";

import {
  ArrowCounterClockwise,
  Brain,
  CaretRight,
  Check,
  Copy,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Fragment, useEffect, useState } from "react";
import { Button, IconButton } from "@/components/ui/action-button";
import { Tooltip } from "@/components/ui/tooltip-hint";
import { EASE_OUT } from "@/lib/motion-tokens";
import { cn } from "@/lib/utils";

export type Citation = { id: string; title: string; url: string; source?: string };

export type StreamingMessageData = {
  content: string;
  status: "streaming" | "done" | "error";
  reasoning?: { text: string; durationMs?: number; streaming?: boolean };
  citations?: Citation[];
  error?: string;
};

export type StreamingMessageProps = {
  data: StreamingMessageData;
  /** Shown in the header, e.g. "Claude Opus 5.5". */
  model?: string;
  /** Hide the avatar + model row when a surrounding thread already shows the author. */
  showHeader?: boolean;
  onCopy?: (content: string) => void;
  onRetry?: () => void;
  className?: string;
};

// Strong ease-out for things entering; exits are quicker than entrances.
const enter = { duration: 0.22, ease: EASE_OUT };
const leave = { duration: 0.15, ease: EASE_OUT };
const fold = {
  initial: { opacity: 0, height: 0 },
  animate: { opacity: 1, height: "auto", transition: enter },
  exit: { opacity: 0, height: 0, transition: leave },
};

export function StreamingMessage({
  data,
  model = "Assistant",
  showHeader = true,
  onCopy,
  onRetry,
  className,
}: StreamingMessageProps) {
  const { content, status, reasoning, citations = [], error } = data;
  const streaming = status === "streaming";
  // Words present on first render (SSR, paused thumbnails) appear without animating in.
  const [settled] = useState(() => countWords(content));

  return (
    <MotionConfig reducedMotion="user">
      <article
        aria-label={`Message from ${model}`}
        aria-busy={streaming}
        className={cn("w-full max-w-xl text-sm", className)}
      >
        {showHeader && (
          <header className="mb-2 flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-full bg-surface-raised">
              <Sparkle weight="fill" className="size-3.5 text-brand" aria-hidden="true" />
            </span>
            <span className="font-medium">{model}</span>
            {streaming && (
              <span className="text-[0.8125rem] text-muted-foreground">Responding…</span>
            )}
          </header>
        )}
        <div className={showHeader ? "pl-8" : undefined}>
          {reasoning && <Reasoning {...reasoning} />}
          {(content || !reasoning?.streaming) && (
            <Content text={content} streaming={streaming} settled={settled} />
          )}
          {citations.length > 0 && !streaming && (
            <ul aria-label="Sources" className="mt-3 flex flex-wrap gap-1.5">
              {citations.map((citation, i) => (
                <motion.li
                  key={citation.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ ...enter, delay: i * 0.04 }}
                >
                  <CitationChip citation={citation} index={i + 1} />
                </motion.li>
              ))}
            </ul>
          )}
          <AnimatePresence initial={false}>
            {status === "error" && (
              <motion.div role="alert" {...fold} className="overflow-hidden">
                <div className="mt-3 flex items-center gap-2.5 rounded-2xl bg-negative/10 py-2 pr-2 pl-3.5">
                  <WarningCircle
                    weight="fill"
                    className="size-4 shrink-0 text-negative"
                    aria-hidden="true"
                  />
                  <p className="flex-1 text-[0.8125rem]">
                    <span className="font-medium text-negative">
                      Response interrupted.{" "}
                    </span>
                    <span className="text-muted-foreground">
                      {error ?? "Something went wrong."}
                    </span>
                  </p>
                  {onRetry && (
                    <Button
                      icon={ArrowCounterClockwise}
                      iconWeight="bold"
                      onClick={onRetry}
                      className="h-7 px-3 text-xs"
                    >
                      Retry
                    </Button>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence initial={false}>
            {status === "done" && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0, transition: enter }}
                exit={{ opacity: 0, transition: leave }}
                className="mt-2 -ml-2 flex items-center gap-0.5"
              >
                <CopyAction content={content} onCopy={onCopy} />
                {onRetry && (
                  <IconButton
                    icon={ArrowCounterClockwise}
                    iconWeight="bold"
                    label="Regenerate response"
                    onClick={onRetry}
                    className="size-7"
                  />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <p role="status" aria-live="polite" className="sr-only">
          {status === "done"
            ? "Response complete"
            : status === "error"
              ? "Response failed"
              : ""}
        </p>
      </article>
    </MotionConfig>
  );
}

function Reasoning({
  text,
  durationMs,
  streaming,
}: NonNullable<StreamingMessageData["reasoning"]>) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? Boolean(streaming);
  const seconds = Math.max(1, Math.round((durationMs ?? 0) / 1000));

  return (
    <div className="mb-3 rounded-2xl bg-foreground/[0.04]">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setUserOpen(!open)}
        className="flex w-full items-center gap-1.5 rounded-2xl px-3.5 py-2.5 text-[0.8125rem] text-muted-foreground transition-[color,scale] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] hover:text-foreground active:scale-[0.99]"
      >
        <Brain weight="fill" className="size-3.5" aria-hidden="true" />
        {streaming ? (
          <motion.span
            initial={{ backgroundPosition: "100% 0" }}
            animate={{ backgroundPosition: "-100% 0" }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
            className="bg-[linear-gradient(90deg,var(--muted-foreground)_35%,var(--foreground)_50%,var(--muted-foreground)_65%)] bg-[length:200%_100%] bg-clip-text text-transparent"
          >
            Thinking…
          </motion.span>
        ) : (
          <span>
            Thought for <span className="tabular-nums">{seconds}s</span>
          </span>
        )}
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.2, ease: [0.77, 0, 0.175, 1] }}
          className="ml-auto inline-flex"
        >
          <CaretRight weight="bold" className="size-3.5" aria-hidden="true" />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div {...fold} className="overflow-hidden">
            <p className="px-3.5 pb-3 text-[0.8125rem] leading-6 text-muted-foreground">
              {text}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

type Segment = { text: string; kind: "text" | "code" | "bold" };

// Unclosed `code` or **bold** at the tail (mid-stream) already renders styled,
// so markdown markers never flash on screen.
function parseInline(paragraph: string): Segment[] {
  return paragraph
    .split(/(`[^`]*(?:`|$)|\*\*[^*]*(?:\*\*|$))/)
    .filter((part) => part && part !== "`" && part !== "**")
    .map((part) =>
      part.startsWith("`")
        ? { text: part.replace(/^`|`$/g, ""), kind: "code" }
        : part.startsWith("**")
          ? { text: part.replace(/^\*\*|\*\*$/g, ""), kind: "bold" }
          : { text: part, kind: "text" },
    );
}

const tokenize = (segment: string) => segment.match(/\S+\s*|\s+/g) ?? [];

function countWords(text: string) {
  return text
    .split(/\n{2,}/)
    .flatMap(parseInline)
    .reduce((sum, segment) => sum + tokenize(segment.text).length, 0);
}

function Content({
  text,
  streaming,
  settled,
}: {
  text: string;
  streaming: boolean;
  settled: number;
}) {
  const paragraphs = text.split(/\n{2,}/);
  let index = 0;

  return (
    <div className="flex flex-col gap-3 leading-6 text-pretty">
      {paragraphs.map((paragraph, p) => (
        <p key={p}>
          {parseInline(paragraph).map((segment, s) => {
            const words = tokenize(segment.text);
            const nodes = words.map((word) => {
              const i = index++;
              return i < settled ? (
                <Fragment key={i}>{word}</Fragment>
              ) : (
                <motion.span
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.25, ease: EASE_OUT }}
                >
                  {word}
                </motion.span>
              );
            });
            if (segment.kind === "code")
              return (
                <code
                  key={s}
                  className="rounded-md bg-foreground/[0.07] px-1 py-px font-mono text-[0.75rem]"
                >
                  {nodes}
                </code>
              );
            if (segment.kind === "bold")
              return (
                <strong key={s} className="font-semibold">
                  {nodes}
                </strong>
              );
            return <Fragment key={s}>{nodes}</Fragment>;
          })}
          {streaming && p === paragraphs.length - 1 && (
            <motion.span
              aria-hidden="true"
              animate={{ opacity: [1, 0, 1] }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] rounded-full bg-brand"
            />
          )}
        </p>
      ))}
    </div>
  );
}

function CitationChip({ citation, index }: { citation: Citation; index: number }) {
  const source = citation.source ?? hostname(citation.url);
  return (
    <Tooltip content={citation.title} align="start">
      <a
        href={citation.url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Source ${index}: ${citation.title} (${source})`}
        className="inline-flex h-6 items-center gap-1.5 rounded-full bg-surface-raised px-2.5 text-xs text-muted-foreground transition-[color,scale] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] hover:text-foreground active:scale-[0.97]"
      >
        <span className="font-mono text-[0.6875rem] text-foreground tabular-nums">
          {index}
        </span>
        <span className="max-w-32 truncate">{source}</span>
      </a>
    </Tooltip>
  );
}

function hostname(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function CopyAction({
  content,
  onCopy,
}: {
  content: string;
  onCopy?: (content: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  return (
    <IconButton
      icon={copied ? Check : Copy}
      iconWeight={copied ? "bold" : "fill"}
      label={copied ? "Copied" : "Copy message"}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(content);
        } catch {}
        setCopied(true);
        onCopy?.(content);
      }}
      className={cn("size-7", copied && "text-positive hover:text-positive")}
    />
  );
}

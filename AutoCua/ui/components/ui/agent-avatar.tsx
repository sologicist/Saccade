"use client";

import { Tooltip } from "@/components/ui/tooltip-hint";
import { cn } from "@/lib/utils";

export type AvatarSize = "xs" | "sm" | "md" | "lg";
export type AvatarStatus = "online" | "away" | "busy" | "working";

export type AvatarProps = {
  name: string;
  /** Image URL; falls back to initials on a tint derived from the name. */
  src?: string;
  size?: AvatarSize;
  /** `agent` is a rounded square, `person` a circle. */
  kind?: "agent" | "person";
  status?: AvatarStatus;
  className?: string;
};

// Tints picked deterministically from the name.
const tints = [
  "#0a84ff",
  "#5e5ce6",
  "#bf5af2",
  "#1a9e8c",
  "#30c05a",
  "#ff9f0a",
  "#ff375f",
];

const sizes: Record<AvatarSize, { box: string; text: string; badge: string }> = {
  xs: { box: "size-5", text: "text-[0.5625rem]", badge: "size-2" },
  sm: { box: "size-7", text: "text-[0.6875rem]", badge: "size-2.5" },
  md: { box: "size-9", text: "text-[0.8125rem]", badge: "size-3" },
  lg: { box: "size-12", text: "text-base", badge: "size-3.5" },
};

const statusLabels: Record<AvatarStatus, string> = {
  online: "online",
  away: "away",
  busy: "busy",
  working: "working",
};

const statusColors: Record<Exclude<AvatarStatus, "working">, string> = {
  online: "bg-positive",
  away: "bg-warning",
  busy: "bg-negative",
};

export function initials(name: string) {
  const words = name
    .trim()
    .split(/[\s._-]+/)
    .filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2)).toUpperCase();
}

export function tintFor(name: string) {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return tints[Math.abs(hash) % tints.length];
}

export function Avatar({
  name,
  src,
  size = "md",
  kind = "person",
  status,
  className,
}: AvatarProps) {
  const s = sizes[size];
  const shape = kind === "agent" ? "rounded-[30%]" : "rounded-full";
  const tint = tintFor(name);

  return (
    <span
      role="img"
      aria-label={status ? `${name}, ${statusLabels[status]}` : name}
      className={cn("relative inline-flex shrink-0", s.box, className)}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- plain img keeps the primitive framework-agnostic
        <img src={src} alt="" className={cn("size-full object-cover", shape)} />
      ) : (
        <span
          aria-hidden="true"
          className={cn(
            "flex size-full items-center justify-center font-medium",
            shape,
            s.text,
          )}
          style={{
            background: `color-mix(in oklab, ${tint} 22%, transparent)`,
            color: tint,
          }}
        >
          {initials(name)}
        </span>
      )}
      {status && (
        // The badge sits in a ring of the page background, so it reads on any surface.
        <span
          aria-hidden="true"
          className={cn(
            "absolute -right-0.5 -bottom-0.5 flex items-center justify-center rounded-full bg-[var(--avatar-gap,var(--background))] p-[2px]",
          )}
        >
          {status === "working" ? (
            <span
              className={cn(
                "block animate-spin rounded-full bg-[conic-gradient(var(--brand)_0_70%,transparent_70%)] motion-reduce:animate-none",
                s.badge,
              )}
              style={{
                mask: "radial-gradient(circle, transparent 38%, #000 40%)",
                WebkitMask: "radial-gradient(circle, transparent 38%, #000 40%)",
              }}
            />
          ) : (
            <span className={cn("block rounded-full", s.badge, statusColors[status])} />
          )}
        </span>
      )}
    </span>
  );
}

export type AvatarGroupProps = {
  people: Omit<AvatarProps, "size" | "className">[];
  size?: AvatarSize;
  /** Avatars shown before collapsing the rest into "+N". */
  max?: number;
  className?: string;
};

const overlap: Record<AvatarSize, string> = {
  xs: "-ml-1",
  sm: "-ml-1.5",
  md: "-ml-2",
  lg: "-ml-3",
};

/**
 * Overlapping avatars. Each one sits in a gap of the surrounding background
 * (set `--avatar-gap` to match a surface), so no outline is needed.
 */
export function AvatarGroup({
  people,
  size = "sm",
  max = 4,
  className,
}: AvatarGroupProps) {
  const shown = people.slice(0, max);
  const rest = people.slice(max);
  const s = sizes[size];

  return (
    <div
      role="group"
      aria-label={`${people.length} participants`}
      className={cn("flex", className)}
    >
      {shown.map((person, i) => (
        <Tooltip key={person.name} content={person.name} side="bottom">
          <span
            tabIndex={0}
            className={cn(
              "relative rounded-full bg-[var(--avatar-gap,var(--background))] p-[2px] outline-offset-0",
              person.kind === "agent" && "rounded-[30%]",
              i > 0 && overlap[size],
            )}
          >
            <Avatar {...person} size={size} />
          </span>
        </Tooltip>
      ))}
      {rest.length > 0 && (
        <Tooltip content={rest.map((p) => p.name).join(", ")} side="bottom">
          <span
            tabIndex={0}
            aria-label={`and ${rest.length} more: ${rest.map((p) => p.name).join(", ")}`}
            className={cn(
              "relative rounded-full bg-[var(--avatar-gap,var(--background))] p-[2px]",
              overlap[size],
            )}
          >
            <span
              className={cn(
                "flex items-center justify-center rounded-full bg-foreground/[0.08] font-medium text-muted-foreground tabular-nums",
                s.box,
                s.text,
              )}
            >
              +{rest.length}
            </span>
          </span>
        </Tooltip>
      )}
    </div>
  );
}

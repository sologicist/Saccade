"use client";

import { CaretRight, Check, type Icon } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ContextMenu as ContextPrimitive, DropdownMenu } from "radix-ui";
import { useState } from "react";
import { EASE_OUT, instant } from "@/lib/motion-tokens";
import { cn } from "@/lib/utils";

// Radix's `asChild`, passed as a spread: the shadcn CLI rewrites a literal
// `asChild` attribute into Base UI's `render` prop for base-* styles, which
// would break these Radix parts after install.
const slot = { asChild: true } as const;

type Base = { id: string; label: React.ReactNode; icon?: Icon; disabled?: boolean };

export type MenuItem =
  | (Base & {
      type?: "item";
      /** Shortcut text shown on the right, e.g. "⌘C". */
      shortcut?: string;
      description?: React.ReactNode;
      destructive?: boolean;
      onSelect?: () => void;
    })
  | (Base & {
      type: "checkbox";
      checked: boolean;
      onCheckedChange: (checked: boolean) => void;
    })
  | {
      type: "radio";
      id: string;
      value: string;
      onValueChange: (value: string) => void;
      options: {
        value: string;
        label: React.ReactNode;
        icon?: Icon;
        disabled?: boolean;
      }[];
    }
  | (Base & { type: "submenu"; items: MenuItem[] });

/** Items separated by spacing, optionally under a small label. */
export type MenuGroup = { id?: string; label?: string; items: MenuItem[] };

// Both Radix menus share the same part names, so one renderer serves both.
type Parts = typeof DropdownMenu;
const contextParts = ContextPrimitive as unknown as Parts;

const surface =
  "z-50 min-w-48 rounded-2xl bg-surface-inset p-1 text-foreground shadow-[0_12px_32px_-12px_rgb(0_0_0/0.28)] outline-none dark:bg-surface-raised dark:shadow-[0_16px_40px_-12px_rgb(0_0_0/0.7)]";
const row =
  "relative flex cursor-default items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-[0.8125rem] outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-40 data-[highlighted]:bg-foreground/[0.07]";

// When any row in a group has an icon, rows without one keep an empty icon
// column so every label starts on the same line.
function Glyph({ icon: IconComponent, reserve }: { icon?: Icon; reserve?: boolean }) {
  if (IconComponent)
    return (
      <IconComponent weight="fill" className="size-4 shrink-0 text-muted-foreground" />
    );
  return reserve ? <span aria-hidden="true" className="size-4 shrink-0" /> : null;
}

const hasIcons = (items: MenuItem[]) =>
  items.some((item) =>
    item.type === "radio" ? item.options.some((o) => o.icon) : !!item.icon,
  );

function Items({ parts: P, groups }: { parts: Parts; groups: MenuGroup[] }) {
  return groups.map((group, g) => (
    <P.Group key={group.id ?? g} className={cn(g > 0 && "mt-1 pt-1")}>
      {group.label && (
        <P.Label className="px-2.5 pt-1 pb-0.5 text-[0.6875rem] font-medium text-muted-foreground">
          {group.label}
        </P.Label>
      )}
      {group.items.map((item) => (
        <Entry key={item.id} parts={P} item={item} reserve={hasIcons(group.items)} />
      ))}
    </P.Group>
  ));
}

function Entry({
  parts: P,
  item,
  reserve,
}: {
  parts: Parts;
  item: MenuItem;
  reserve: boolean;
}) {
  if (item.type === "checkbox") {
    return (
      <P.CheckboxItem
        className={row}
        checked={item.checked}
        onCheckedChange={item.onCheckedChange}
        disabled={item.disabled}
        onSelect={(event) => event.preventDefault()}
      >
        <Glyph icon={item.icon} reserve={reserve} />
        <span className="flex-1">{item.label}</span>
        <P.ItemIndicator>
          <Check weight="bold" className="size-3.5 text-brand" />
        </P.ItemIndicator>
      </P.CheckboxItem>
    );
  }
  if (item.type === "radio") {
    return (
      <P.RadioGroup value={item.value} onValueChange={item.onValueChange}>
        {item.options.map((option) => (
          <P.RadioItem
            key={option.value}
            value={option.value}
            disabled={option.disabled}
            className={row}
          >
            <Glyph icon={option.icon} reserve={reserve} />
            <span className="flex-1">{option.label}</span>
            <P.ItemIndicator>
              <Check weight="bold" className="size-3.5 text-brand" />
            </P.ItemIndicator>
          </P.RadioItem>
        ))}
      </P.RadioGroup>
    );
  }
  if (item.type === "submenu") {
    return (
      <P.Sub>
        <P.SubTrigger className={cn(row, "data-[state=open]:bg-foreground/[0.07]")}>
          <Glyph icon={item.icon} reserve={reserve} />
          <span className="flex-1">{item.label}</span>
          <CaretRight weight="bold" className="size-3 text-muted-foreground" />
        </P.SubTrigger>
        <P.Portal>
          <P.SubContent sideOffset={6} alignOffset={-4} {...slot}>
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.15, ease: EASE_OUT }}
              style={{
                transformOrigin:
                  "var(--radix-dropdown-menu-content-transform-origin, var(--radix-context-menu-content-transform-origin))",
              }}
              className={surface}
            >
              <Items parts={P} groups={[{ items: item.items }]} />
            </motion.div>
          </P.SubContent>
        </P.Portal>
      </P.Sub>
    );
  }
  return (
    <P.Item
      className={cn(
        row,
        item.destructive && "text-negative data-[highlighted]:bg-negative/10",
      )}
      disabled={item.disabled}
      onSelect={item.onSelect}
    >
      {item.icon ? (
        <item.icon
          weight="fill"
          className={cn(
            "size-4 shrink-0",
            item.destructive ? "text-negative" : "text-muted-foreground",
          )}
        />
      ) : (
        <Glyph reserve={reserve} />
      )}
      <span className="min-w-0 flex-1">
        <span className="block">{item.label}</span>
        {item.description && (
          <span className="block text-xs text-muted-foreground">{item.description}</span>
        )}
      </span>
      {item.shortcut && (
        <kbd className="font-sans text-xs text-muted-foreground">{item.shortcut}</kbd>
      )}
    </P.Item>
  );
}

/** Keyboard-opened menus appear instantly; pointer-opened ones grow from the trigger. */
function useOpenMotion() {
  const reduce = useReducedMotion();
  const [viaKeyboard, setViaKeyboard] = useState(false);
  const still = viaKeyboard || !!reduce;
  return {
    setViaKeyboard,
    content: (originVar: string) => ({
      initial: { opacity: 0, scale: reduce ? 1 : 0.97 },
      animate: {
        opacity: 1,
        scale: 1,
        transition: still ? instant : { duration: 0.16, ease: EASE_OUT },
      },
      exit: {
        opacity: 0,
        scale: reduce ? 1 : 0.98,
        transition: still ? instant : { duration: 0.1, ease: EASE_OUT },
      },
      style: { transformOrigin: `var(${originVar})` },
    }),
  };
}

export type MenuProps = {
  /** A single button-like element that opens the menu. */
  trigger: React.ReactElement;
  groups: MenuGroup[];
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

/** Dropdown menu opened from a trigger button. */
export function Menu({
  trigger,
  groups,
  side = "bottom",
  align = "start",
  open: openProp,
  onOpenChange,
  className,
}: MenuProps) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = (next: boolean) => {
    setOpenState(next);
    onOpenChange?.(next);
  };
  const { setViaKeyboard, content } = useOpenMotion();

  return (
    <DropdownMenu.Root open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger
        {...slot}
        onPointerDown={() => setViaKeyboard(false)}
        onKeyDown={(event) => {
          if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key))
            setViaKeyboard(true);
        }}
      >
        {trigger}
      </DropdownMenu.Trigger>
      <AnimatePresence>
        {open && (
          <DropdownMenu.Portal forceMount>
            <DropdownMenu.Content
              forceMount
              {...slot}
              side={side}
              align={align}
              sideOffset={6}
              collisionPadding={8}
            >
              <motion.div
                {...content("--radix-dropdown-menu-content-transform-origin")}
                className={cn(surface, className)}
              >
                <Items parts={DropdownMenu} groups={groups} />
              </motion.div>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        )}
      </AnimatePresence>
    </DropdownMenu.Root>
  );
}

export type ContextMenuProps = {
  /** The area that opens the menu on right-click or long-press. */
  children: React.ReactElement;
  groups: MenuGroup[];
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

/** Right-click (or long-press, or the context-menu key) menu for an area. */
export function ContextMenu({
  children,
  groups,
  onOpenChange,
  className,
}: ContextMenuProps) {
  const [open, setOpen] = useState(false);
  const { setViaKeyboard, content } = useOpenMotion();

  return (
    <ContextPrimitive.Root
      onOpenChange={(next) => {
        setOpen(next);
        onOpenChange?.(next);
      }}
    >
      <ContextPrimitive.Trigger
        {...slot}
        onPointerDown={() => setViaKeyboard(false)}
        onKeyDown={(event) => {
          if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10"))
            setViaKeyboard(true);
        }}
      >
        {children}
      </ContextPrimitive.Trigger>
      <AnimatePresence>
        {open && (
          <ContextPrimitive.Portal forceMount>
            <ContextPrimitive.Content forceMount {...slot} collisionPadding={8}>
              <motion.div
                {...content("--radix-context-menu-content-transform-origin")}
                className={cn(surface, className)}
              >
                <Items parts={contextParts} groups={groups} />
              </motion.div>
            </ContextPrimitive.Content>
          </ContextPrimitive.Portal>
        )}
      </AnimatePresence>
    </ContextPrimitive.Root>
  );
}

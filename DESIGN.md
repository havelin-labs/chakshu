# Chakshu design system

Chakshu uses the Havelin design system, the same visual language as havelin.in, adapted for a product UI. Use this file, not memory, when building or changing the portal or the docs.

## Brand

- Product: **Chakshu** (चक्षु, "the eye"), by Havelin.
- Tagline: "Pull request reviews for your teams."
- Docs: chakshu.havelin.in/docs

### Logo

Drawn in Havelin's line-drawn node/link style: an eye outline whose two corners are teal nodes, with a teal iris. The wordmark is "Chakshu" in Space Grotesk 700.

| File | Use |
|---|---|
| `brand/logo.svg` | Horizontal lockup for READMEs, docs and slides (light backgrounds) |
| `frontend/public/favicon.svg` | Square mark on a light disc, for browser tabs and avatars |
| `frontend/src/components/logo.tsx` | `<Logo />` and `<LogoMark />` in the portal. Lines use `currentColor`, so they follow dark mode. |

Don't recolor the mark, fill the eye, or stretch it.

## Fonts

| Element | Font | Weight | Size |
|---|---|---|---|
| h1 (page) | Space Grotesk | 700 | 36px (`text-4xl`) |
| h2 (section) | Space Grotesk | 700 | 24-30px |
| h3 (card title) | Space Grotesk | 600 | 18px |
| Body | Inter | 400 | 16px |
| Eyebrow / badge | Inter | 600 | 12px, uppercase, wide tracking |
| Primary button | Inter | 600 | 14px |
| Secondary button / nav | Inter | 500 | 14px |

The portal bundles both fonts (`@fontsource-variable/space-grotesk`, `@fontsource-variable/inter`) so self-hosted installs work offline. The docs site is public and loads them from Google Fonts.

## Colors

| Token | Light | Dark | Usage |
|---|---|---|---|
| `background` | `#F4F5F6` | `#0B0C0E` | Page, header, footer |
| `card` | `#FFFFFF` | `#131518` | Cards, popovers |
| `foreground` | `#0A0A0A` | `#F4F5F6` | Text, headings, logo lines |
| `muted-foreground` | `#5E6773` | `#9AA3AE` | Body copy, secondary text |
| `primary` / `brand-teal` | `#00C7B0` | `#00C7B0` | Buttons, badges, focus rings, logo nodes |
| `brand-teal-ink` | `#00806F` | `#2EE0CA` | Teal **text** (links, eyebrows) |
| `brand-teal-tint` | `rgba(164,239,230,0.2)` | `rgba(0,199,176,0.08)` | Highlighted sections |
| `border` | `rgba(204,207,209,0.5)` | `rgba(255,255,255,0.08)` | Hairlines |

### Contrast rules

- Teal backgrounds carry **dark** text (`#0A0A0A` on `#00C7B0` is about 9:1). White on teal is about 2:1, so never use it.
- Teal text on the light background uses `brand-teal-ink`, not `#00C7B0`.
- Havelin's marketing site is light-only. Chakshu adds a dark mode that follows the OS, using the dark column above.

All tokens live in `frontend/src/index.css`. Tailwind classes: `bg-primary`, `text-brand-teal-ink`, `border-brand-teal/30`, `bg-brand-teal-tint`.

## Shape and spacing

- Radius: 4px everywhere (`--radius: 0.25rem`).
- Button padding: `8px 20px`.
- Badge / eyebrow: `4px 12px`, 1px border at 30% teal.
- Content width: `max-w-6xl` with `px-6`; page sections `py-16`.
- Header: sticky, `bg-background/90` with backdrop blur and a bottom hairline.

## Background grid

A faint 60px line grid sits behind every page: the `bg-havelin-grid` utility at `opacity-[0.03]`.

```tsx
<div className="bg-havelin-grid pointer-events-none absolute inset-0 opacity-[0.03]" aria-hidden />
```

## Components

| Component | Where | Notes |
|---|---|---|
| `Logo`, `LogoMark` | `components/logo.tsx` | Header and anywhere the brand appears |
| `Eyebrow` | `components/eyebrow.tsx` | Above page and section headings |
| `Button`, `Badge`, `Card` | `components/ui/` | shadcn/ui, themed by the tokens above |

Prefer Tailwind utilities over custom CSS so diffs stay readable.

## Copy

- Plain, direct sentences. Say what to do and what the reader will see.
- No em dashes; use commas, colons or full stops.
- Sentence case for headings and buttons ("Run review", not "Run Review").

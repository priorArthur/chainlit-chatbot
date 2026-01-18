# Chainlit Customization Quick Reference

Quick reference for branding this Chainlit app. All customization files go in the `/public` folder.

---

## Directory Structure

```
public/
├── logo_dark.png          # Logo for dark mode
├── logo_light.png         # Logo for light mode
├── favicon.png            # Browser tab icon
├── theme.json             # Color/font theming
├── stylesheet.css         # Custom CSS overrides
└── avatars/
    └── your_dscr_agent.png  # Avatar for assistant
```

---

## 1. Logo & Favicon

**Location:** `/public/`

| File | Purpose |
|------|---------|
| `logo_dark.png` | Displayed in dark mode |
| `logo_light.png` | Displayed in light mode |
| `favicon.png` | Browser tab icon |

No config needed - Chainlit auto-detects these files on restart.

**Note:** Clear browser cache if changes don't appear.

---

## 2. Theme (Colors & Fonts)

**Location:** `/public/theme.json`

```json
{
  "light": {
    "--font-sans": "'Inter', sans-serif",
    "--font-mono": "'Fira Code', monospace",
    "--background": "0 0% 100%",
    "--foreground": "240 10% 4%",
    "--primary": "221 83% 53%",
    "--secondary": "240 5% 96%",
    "--muted": "240 5% 96%",
    "--accent": "240 5% 96%",
    "--destructive": "0 84% 60%",
    "--border": "240 6% 90%",
    "--input": "240 6% 90%",
    "--ring": "221 83% 53%",
    "--card": "0 0% 100%",
    "--sidebar-background": "0 0% 98%",
    "--sidebar-foreground": "240 5% 26%",
    "--sidebar-primary": "221 83% 53%",
    "--sidebar-accent": "240 5% 96%",
    "--sidebar-border": "240 6% 90%",
    "--radius": "0.5rem"
  },
  "dark": {
    "--background": "240 10% 4%",
    "--foreground": "0 0% 98%",
    "--primary": "221 83% 53%",
    "--secondary": "240 4% 16%",
    "--muted": "240 4% 16%",
    "--accent": "240 4% 16%",
    "--destructive": "0 63% 31%",
    "--border": "240 4% 16%",
    "--input": "240 4% 16%",
    "--ring": "221 83% 53%",
    "--card": "240 10% 4%",
    "--sidebar-background": "240 6% 10%",
    "--sidebar-foreground": "240 5% 65%",
    "--sidebar-primary": "221 83% 53%",
    "--sidebar-accent": "240 4% 16%",
    "--sidebar-border": "240 4% 16%",
    "--radius": "0.5rem"
  },
  "custom_fonts": [
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
  ]
}
```

**Color format:** HSL values without `hsl()` wrapper (e.g., `"221 83% 53%"` not `"#3b82f6"`)

**Hex to HSL converter:** https://htmlcolors.com/hex-to-hsl

---

## 3. Custom CSS

**Location:** `/public/stylesheet.css`

**Enable in** `.chainlit/config.toml`:

```toml
[UI]
custom_css = '/public/stylesheet.css'
```

**Example CSS:**

```css
/* Hide Chainlit branding */
.watermark {
  display: none !important;
}

/* Custom message bubble styling */
.message-content {
  border-radius: 12px;
}

/* Custom scrollbar */
::-webkit-scrollbar {
  width: 8px;
}
```

**Discovery:** Use browser DevTools (Inspect Element) to find CSS class names to override.

---

## 4. Avatars

**Location:** `/public/avatars/`

**Naming convention:** Lowercase, underscores for spaces, match the assistant name.

| Assistant Name | Avatar File |
|----------------|-------------|
| `Your DSCR Agent` | `your_dscr_agent.png` |
| `My Assistant` | `my_assistant.png` |

**Format:** PNG recommended

**Default:** Uses favicon if no avatar file found.

---

## 5. Login Page Background (Optional)

If using authentication, customize in `.chainlit/config.toml`:

```toml
[UI]
login_page_image = "/public/login-bg.jpg"
login_page_image_filter = "brightness-50"
login_page_image_dark_filter = "brightness-30"
```

---

## Implementation Checklist

1. [ ] Create `/public` folder if it doesn't exist
2. [ ] Add `logo_light.png` and `logo_dark.png`
3. [ ] Add `favicon.png`
4. [ ] Create `theme.json` with brand colors (HSL format)
5. [ ] Create `stylesheet.css` for any CSS overrides
6. [ ] Update `.chainlit/config.toml` to enable custom CSS
7. [ ] Add `avatars/your_dscr_agent.png`
8. [ ] Restart app and clear browser cache

---

## Source Docs

- [Logo & Favicon](https://docs.chainlit.io/customisation/custom-logo-and-favicon)
- [Theme](https://docs.chainlit.io/customisation/theme)
- [Custom CSS](https://docs.chainlit.io/customisation/custom-css)
- [Avatars](https://docs.chainlit.io/customisation/avatars)

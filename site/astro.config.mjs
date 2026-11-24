// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
// Declared in package.json (Starlight also depends on it); configured here so the sitemap can leave out noindex pages
// and carry <lastmod>.
import sitemap from "@astrojs/sitemap";
import { REPO_URL, SITE_URL, BASE, PREVIEW, GOOGLE_VERIFICATION, BING_VERIFICATION } from "./site.config.mjs";
import { excludedPaths, lastmodByPath, lastmodFor } from "./sitemap-config.mjs";
// Astro's own Markdown processor (a dependency of astro), extended with one hast plugin.
import { satteri } from "@astrojs/markdown-satteri";
import ohgA11y from "./src/lib/rehype-a11y.mjs";

const base = BASE.endsWith("/") ? BASE : BASE + "/";
const sitemapExcluded = excludedPaths();
const sitemapDates = lastmodByPath();
/** A sitemap URL -> its path without the site and base ("/pokemon/cyndaquil/"). */
const sitePath = (url) => "/" + new URL(url).pathname.slice(base.length);
const DISCORD_URL = "https://discord.gg/sQY2udrQS";

export default defineConfig({
  site: SITE_URL,
  base,
  trailingSlash: "always",
  // Table names and lang tags for Chinese/Japanese text in Markdown and MDX pages (src/lib/rehype-a11y.mjs).
  markdown: { processor: satteri({ hastPlugins: [ohgA11y] }) },
  integrations: [
    sitemap({
      filter: (page) => !sitemapExcluded.has(sitePath(page)),
      serialize: (item) => {
        const lastmod = lastmodFor(sitemapDates, sitePath(item.url));
        return lastmod ? { ...item, lastmod } : item;
      },
    }),
    starlight({
      title: "Origin HeartGold English",
      description:
        "The official site of the Origin HeartGold English translation: the English patch, a walkthrough and quest guide, Pokédex, locations, items and trainers for Origin HeartGold (起源心金) v4.0.3.",
      social: [
        { icon: "github", label: "GitHub", href: REPO_URL },
        { icon: "discord", label: "Discord", href: DISCORD_URL },
      ],
      routeMiddleware: "./src/routeData.ts",
      customCss: ["./src/styles/custom.css"],
      lastUpdated: false,
      pagination: true,
      head: [
        { tag: "meta", attrs: { name: "ohg-repo", content: REPO_URL } },
        // Icons: the OHG monogram (public/favicon.svg is Starlight's favicon); sources and renderer in site/brand/.
        { tag: "link", attrs: { rel: "icon", href: base + "favicon.ico", sizes: "32x32" } },
        { tag: "link", attrs: { rel: "icon", type: "image/png", href: base + "favicon-96.png", sizes: "96x96" } },
        { tag: "link", attrs: { rel: "apple-touch-icon", href: base + "apple-touch-icon.png" } },
        { tag: "link", attrs: { rel: "manifest", href: base + "site.webmanifest" } },
        { tag: "meta", attrs: { name: "theme-color", content: "#faf9f5", media: "(prefers-color-scheme: light)" } },
        { tag: "meta", attrs: { name: "theme-color", content: "#111923", media: "(prefers-color-scheme: dark)" } },
        // The phone layout's switches, set before the first paint. ohg.js (deferred) keeps them current, but on a long
        // page (the Pokédex, the Items list) it runs after the table has already been drawn in its wide form.
        // data-ohg-list marks the other lists, whose introductions a phone leaves out. A page that ohg.js rebuilds
        // for a phone (the guide's chapters, a Pokémon, a move…) stays hidden until that is done, 2 s at most.
        { tag: "script", content: `try{var d=document.documentElement,p=matchMedia("(max-width: 50rem)").matches,l=location.pathname.replace(/index\\.html$/,"").slice(${base.length});d.toggleAttribute("data-ohg-phone",p);d.toggleAttribute("data-ohg-home",l==="");if(/^(moves|abilities|locations|tms|tutors)\\/$/.test(l))d.setAttribute("data-ohg-list","");if(p&&/^(guide\\/|(tms|locations|trainers)\\/$|(pokemon|items|moves|abilities|locations|trainers)\\/.)/.test(l)){d.setAttribute("data-ohg-pending","");setTimeout(function(){d.removeAttribute("data-ohg-pending")},2000)}}catch(e){}` },
        { tag: "script", attrs: { src: base + "ohg.js", defer: true } },
        // Pokémon images come from PokéAPI's sprite repository (W-050, W-052). Images are no-CORS requests: no crossorigin.
        { tag: "link", attrs: { rel: "preconnect", href: "https://raw.githubusercontent.com" } },
        ...(PREVIEW ? [{ tag: "meta", attrs: { name: "robots", content: "noindex, nofollow" } }] : []),
        ...(!PREVIEW && GOOGLE_VERIFICATION ? [{ tag: "meta", attrs: { name: "google-site-verification", content: GOOGLE_VERIFICATION } }] : []),
        ...(!PREVIEW && BING_VERIFICATION ? [{ tag: "meta", attrs: { name: "msvalidate.01", content: BING_VERIFICATION } }] : []),
        ...(PREVIEW ? [] : [{
          tag: "script",
          // Only load analytics on the configured public site, never local or /preview/ builds.
          content: `if (location.protocol === "https:" && location.origin === ${JSON.stringify(new URL(SITE_URL).origin)}) {
            const script = document.createElement("script");
            script.dataset.goatcounter = "https://originheartgold.goatcounter.com/count";
            script.async = true;
            script.src = "https://gc.zgo.at/count.js";
            document.head.append(script);
          }`,
        }]),
      ],
      components: {
        MobileMenuToggle: "./src/components/MobileMenuToggle.astro",
        PageTitle: "./src/components/PageTitle.astro",
        SiteTitle: "./src/components/SiteTitle.astro",
        Hero: "./src/components/Hero.astro",
        Footer: "./src/components/Footer.astro",
        Header: "./src/components/GuideHeader.astro",
        Sidebar: "./src/components/Sidebar.astro",
        Banner: "./src/components/Banner.astro",
      },
      sidebar: [
        {
          label: "Start here",
          items: [
            { label: "Home", link: "/" },
            { label: "Patch your game", slug: "patch" },
            { label: "FAQ", slug: "faq" },
            { label: "Changelog and contributors", link: "/changelog/" },
            { label: "Save editor", link: "/save-editor/" },
            { label: "How to use this guide", slug: "about" },
            { label: "Mechanics and controls", slug: "mechanics" },
            { label: "Difficulty settings", slug: "difficulty" },
            { label: "Camera and widescreen codes", slug: "camera-codes" },
          ],
        },
        {
          label: "Quest guide",
          items: [{ autogenerate: { directory: "guide" } }],
        },
        {
          label: "Reference",
          items: [
            { label: "Pokémon", link: "/pokemon/" },
            { label: "Team Builder", link: "/team-builder/" },
            { label: "Damage calculator", link: "/damage-calc/" },
            { label: "Locations", link: "/locations/" },
            { label: "Calendar encounters", slug: "calendar" },
            { label: "Items", link: "/items/" },
            { label: "Moves", link: "/moves/" },
            { label: "TMs and HMs", link: "/tms/" },
            { label: "Abilities", link: "/abilities/" },
            { label: "Overworld abilities", slug: "overworld-abilities" },
            { label: "Type changes", link: "/type-changes/" },
            { label: "Base stat changes", link: "/stat-changes/" },
            { label: "Apricorn trees", slug: "apricorn-trees" },
            { label: "Trainers", link: "/trainers/" },
            { label: "Move tutors", link: "/tutors/" },
            { label: "Reference sources", link: "/reference-sources/" },
          ],
        },
        {
          label: "Help out",
          items: [
            { label: "Report a problem or contribute", slug: "contribute" },
          ],
        },
      ],
    }),
  ],
  devToolbar: {
    enabled: false,
  },
  vite: {
    // Keep /*! @license */ banners (the damage engine's MIT notice) in minified bundles.
    build: { rolldownOptions: { output: { comments: { legal: true } } } },
  },
});

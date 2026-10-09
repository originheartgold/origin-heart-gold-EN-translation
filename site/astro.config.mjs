// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import { REPO_URL, SITE_URL, BASE } from "./site.config.mjs";

const base = BASE.endsWith("/") ? BASE : BASE + "/";

export default defineConfig({
  site: SITE_URL,
  base,
  trailingSlash: "always",
  integrations: [
    starlight({
      title: "Origin HeartGold Guide",
      description:
        "Quest guide, Pokédex, locations, items and trainers for Origin HeartGold (起源心金) v4.0.3 in English.",
      social: [{ icon: "github", label: "GitHub", href: REPO_URL }],
      customCss: ["./src/styles/custom.css"],
      lastUpdated: false,
      pagination: true,
      head: [
        { tag: "meta", attrs: { name: "ohg-repo", content: REPO_URL } },
        { tag: "script", attrs: { src: base + "ohg.js", defer: true } },
        {
          tag: "script",
          // Only load analytics on the configured public site, never local previews.
          content: `if (location.protocol === "https:" && location.origin === ${JSON.stringify(new URL(SITE_URL).origin)}) {
            const script = document.createElement("script");
            script.dataset.goatcounter = "https://originheartgold.goatcounter.com/count";
            script.async = true;
            script.src = "https://gc.zgo.at/count.js";
            document.head.append(script);
          }`,
        },
      ],
      components: {
        PageTitle: "./src/components/PageTitle.astro",
        SiteTitle: "./src/components/SiteTitle.astro",
        Hero: "./src/components/Hero.astro",
        Footer: "./src/components/Footer.astro",
        Header: "./src/components/GuideHeader.astro",
      },
      sidebar: [
        {
          label: "Start here",
          items: [
            { label: "Home", link: "/" },
            { label: "Patch your game", slug: "patch" },
            { label: "FAQ", slug: "faq" },
            { label: "Save editor", link: "/save-editor/" },
            { label: "How to use this guide", slug: "about" },
            { label: "Mechanics and controls", slug: "mechanics" },
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
            { label: "Locations", link: "/locations/" },
            { label: "Calendar encounters", slug: "calendar" },
            { label: "Items", link: "/items/" },
            { label: "Moves", link: "/moves/" },
            { label: "TMs and HMs", link: "/tms/" },
            { label: "Abilities", link: "/abilities/" },
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
});

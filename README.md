# ADeclercq - Personal Academic Website

This repository contains the source code for my personal academic website, built with [Quarto](https://quarto.org/) and published via [GitHub Pages](https://pages.github.com/). The site is available at [https://arthurdeclercq.bio](https://arthurdeclercq.bio).

## Features

- Fully custom HTML and CSS (no template dependencies)
- Responsive navigation and smooth scrolling
- Custom domain support with `CNAME` preservation
- Organized sections for:
  - About
  - Experience and Education
  - Skills
  - Publications (auto-sorted by date and authorship using data attributes)
  - Projects with GitHub links
  - Contact and social links

## Technical Highlights

- **Built with:** [Quarto](https://quarto.org/) (`_quarto.yml` config)
- **Deployed on:** `gh-pages` branch using `quarto publish gh-pages`
- **Domain:** `arthurdeclercq.bio` (custom domain)
- **Tagging and sorting:** JavaScript-enhanced sorting and tagging for new and first-author publications
- **Styling:** Custom stylesheet (`styles.css`) and Google Fonts (`Cormorant Garamond`)

## Development

To update the site:

# Publish to GitHub Pages
quarto publish gh-pages

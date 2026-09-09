import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { metaForPath, SITE_URL } from './seo'
import { peekDataset } from './data'

function setMeta(selector: string, attr: string, key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(selector)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.rel = 'canonical'
    document.head.appendChild(el)
  }
  el.href = href
}

/**
 * Keep the document head in step with the current route.
 *
 * The prerenderer writes the same values into the static HTML, so the first
 * paint is already correct for a crawler; this exists so a client-side
 * navigation does not leave the previous page's title and description in
 * place. Both read `metaForPath`, so they cannot disagree.
 */
export function useSeo(): void {
  const { pathname } = useLocation()

  useEffect(() => {
    const meta = metaForPath(pathname, peekDataset())
    const canonical = `${SITE_URL}${meta.path === '/' ? '' : meta.path}`

    document.title = meta.title
    setMeta('meta[name="description"]', 'name', 'description', meta.description)
    setMeta('meta[property="og:title"]', 'property', 'og:title', meta.title)
    setMeta(
      'meta[property="og:description"]',
      'property',
      'og:description',
      meta.description,
    )
    setMeta('meta[property="og:url"]', 'property', 'og:url', canonical)
    setMeta('meta[name="twitter:title"]', 'name', 'twitter:title', meta.title)
    setMeta(
      'meta[name="twitter:description"]',
      'name',
      'twitter:description',
      meta.description,
    )
    setCanonical(canonical)
  }, [pathname])
}

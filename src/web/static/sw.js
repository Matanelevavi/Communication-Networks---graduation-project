/*
 * The service worker: it keeps the page itself available without a connection.
 *
 * What it does NOT do is touch /api. A forecast is dynamic, and a family's
 * names ride in the request, so nothing under /api is ever cached here: offline,
 * the page falls back to the last forecast it saved on the device itself, and
 * says so.
 *
 * Pages and scripts are fetched from the network first and only fall back to
 * the cache, so a new release is picked up on the next load instead of being
 * hidden behind an old copy.
 */
"use strict";

const VERSION = "weatherwear-v3";
const SHELL = ["./", "styles.css", "app.js", "icon.svg", "icon-192.png", "manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name !== VERSION).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only our own pages and files, only reads, and never the API.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.includes("/api/")) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(VERSION).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("./"))),
  );
});

const API_HEALTH_PATHS = new Map([
  ['/api/health', '/health'],
  ['/api/ready', '/ready'],
]);

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=UTF-8',
      'cache-control': 'no-store',
    },
  });
}

async function proxyApi(request, env, url) {
  const apiOrigin = String(env.API_ORIGIN || '').trim().replace(/\/$/, '');

  if (!apiOrigin) {
    return jsonResponse(
      {
        status: 'unavailable',
        error: 'API_ORIGIN is not configured',
      },
      503
    );
  }

  let origin;
  try {
    origin = new URL(apiOrigin);
  } catch {
    return jsonResponse(
      {
        status: 'unavailable',
        error: 'API_ORIGIN is invalid',
      },
      500
    );
  }

  if (!['http:', 'https:'].includes(origin.protocol)) {
    return jsonResponse(
      {
        status: 'unavailable',
        error: 'API_ORIGIN must use HTTP or HTTPS',
      },
      500
    );
  }

  const backendPath = API_HEALTH_PATHS.get(url.pathname) || url.pathname;
  const upstream = new URL(backendPath + url.search, origin);

  const headers = new Headers(request.headers);
  headers.set('X-Forwarded-Host', url.host);
  headers.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

  try {
    return await fetch(
      new Request(upstream.toString(), {
        method: request.method,
        headers,
        body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
        redirect: 'manual',
      })
    );
  } catch (error) {
    return jsonResponse(
      {
        status: 'unavailable',
        error: 'Backend API is unreachable',
      },
      502
    );
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
      return proxyApi(request, env, url);
    }

    return env.ASSETS.fetch(request);
  },
};

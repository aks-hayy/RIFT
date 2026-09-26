export function rootRedirectHtml() {
    return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="/rift-logo-concept-v9.png" type="image/png">
    <meta http-equiv="refresh" content="0;url=/workloads">
    <title>Opening Workload Deploy — RIFT</title>
    <script>window.location.replace("/workloads")</script>
  </head>
  <body>
    <p>Opening RIFT Workload Deploy…</p>
    <p>If you are not redirected, <a href="/workloads">Workload Deploy</a>.</p>
  </body>
</html>
`;
}

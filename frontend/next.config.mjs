const config = {
  ...(process.env.CATMS_SOURCE_ROOT ? { turbopack: { root: process.env.CATMS_SOURCE_ROOT } } : {}),
  ...(process.env.CATMS_BUILD_THREADS === '1' ? { experimental: { workerThreads: true, cpus: 2, useTypeScriptCli: false } } : {}),
  async rewrites() {
    const backend=(process.env.DJANGO_API_URL || 'http://127.0.0.1:8000').replace(/\/$/,'');
    return [{source:'/api/frontend/:path*',destination:`${backend}/api/frontend/:path*/`}];
  },
  skipTrailingSlashRedirect:true,
};
export default config;

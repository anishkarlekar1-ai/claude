'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const { scanProject } = require('./scan');
const { getGitInfo } = require('./git');
const { loadBoard, addTask, updateTask, deleteTask } = require('./board');

const PUBLIC_DIR = path.join(__dirname, '..', 'public');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8'
};

function sendJson(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body)
  });
  res.end(body);
}

function serveStatic(res, filePath) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
      return;
    }
    const ext = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
      if (data.length > 1e6) {
        reject(new Error('Payload too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!data) return resolve({});
      try {
        resolve(JSON.parse(data));
      } catch (e) {
        reject(e);
      }
    });
    req.on('error', reject);
  });
}

function startServer(root, port) {
  const server = http.createServer(async (req, res) => {
    const parsed = url.parse(req.url, true);
    const pathname = parsed.pathname;

    try {
      if (pathname === '/api/meta' && req.method === 'GET') {
        return sendJson(res, 200, { root });
      }

      if (pathname === '/api/scan' && req.method === 'GET') {
        return sendJson(res, 200, scanProject(root));
      }

      if (pathname === '/api/git' && req.method === 'GET') {
        return sendJson(res, 200, getGitInfo(root));
      }

      if (pathname === '/api/board' && req.method === 'GET') {
        return sendJson(res, 200, loadBoard(root));
      }

      if (pathname === '/api/board/tasks' && req.method === 'POST') {
        const body = await readBody(req);
        const task = addTask(root, body);
        return sendJson(res, 201, task);
      }

      const taskMatch = pathname.match(/^\/api\/board\/tasks\/([^/]+)$/);
      if (taskMatch && req.method === 'PATCH') {
        const body = await readBody(req);
        const task = updateTask(root, taskMatch[1], body);
        if (!task) return sendJson(res, 404, { error: 'Task not found' });
        return sendJson(res, 200, task);
      }
      if (taskMatch && req.method === 'DELETE') {
        const removed = deleteTask(root, taskMatch[1]);
        return sendJson(res, removed ? 200 : 404, { removed });
      }

      // Static file serving
      let filePath = pathname === '/' ? '/index.html' : pathname;
      filePath = path.normalize(filePath).replace(/^(\.\.[/\\])+/, '');
      const fullPath = path.join(PUBLIC_DIR, filePath);
      if (!fullPath.startsWith(PUBLIC_DIR)) {
        res.writeHead(403);
        return res.end('Forbidden');
      }
      return serveStatic(res, fullPath);
    } catch (err) {
      return sendJson(res, 500, { error: err.message });
    }
  });

  server.listen(port, () => {
    console.log('');
    console.log('  CodeCompass is running:');
    console.log('  -> http://localhost:' + port);
    console.log('');
    console.log('  Project: ' + root);
    console.log('  Press Ctrl+C to stop.');
    console.log('');
  });

  return server;
}

module.exports = { startServer };

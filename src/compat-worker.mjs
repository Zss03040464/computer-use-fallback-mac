import { RuntimeWorker } from './runtime-worker.mjs';


export class CompatWorker extends RuntimeWorker {
  constructor(options = {}) {
    super({
      ...options,
      moduleName: 'runtime.compat_worker',
      moduleArgs: [],
    });
  }
}

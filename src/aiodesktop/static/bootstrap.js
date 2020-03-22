(() => {
    let {ws, fn} = window.__aiodesktop__;
    let initFunction = window[fn];

    /**
     * Abstraction over websocket to send & receive json.
     */
    class Channel {
        constructor() {
            this.onOpened = null;
            this.onMessage = null;
            this.onError = null;
            this.onClose = null;

            this.ws = new WebSocket(ws);
            this.ws.onopen = () => {
                this.onOpened && this.onOpened();
            };
            this.ws.onmessage = (e) => {
                this.onMessage && this.onMessage(JSON.parse(e.data));
            };
            this.ws.onerror = (e) => {
                this.onError && this.onError(e);
            };
            this.ws.onclose = () => {
                this.onClose && this.onClose();
            };
        }

        send(data) {
            this.ws.send(JSON.stringify(data));
        }

        close() {
            this.ws.close();
        }
    }

    function getInvoker(executeFn) {
        return new Proxy({}, {
            get(target, attr) {
                if (attr in target) {
                    return target[attr]
                } else {
                    return async (...args) => await executeFn(attr, [...args]);
                }
            }
        });
    }

    class Server {
        /**
         * Expose function or a set of functions to a server.
         *
         * @param {Function|Object.<string, Function>} fnOrFns
         */
        expose(fnOrFns) {
            let mapping;

            if (typeof (fnOrFns) === 'function') {
                mapping = {};
                mapping[fnOrFns.name] = fnOrFns;
            } else {
                mapping = fnOrFns;
            }
            Object.entries(mapping).forEach(([name, fn]) => {
                if (this._fns.hasOwnProperty(name))
                    throw `function '${name}' is already registered`;
                else
                    this._fns[name] = fn;
            });
        }

        /**
         * Execute function on server.
         *
         * @param {String} name - function name
         * @param {Object[]} args - positional arguments
         * @returns {Promise<Object>} - promise with return value
         */
        async execute(name, args) {
            this._idCounter += 1;
            let callId = this._idCounter.toString(10);
            let result = new Promise((resolve, reject) => {
                this._addReturn(callId, resolve, reject)
            });
            await this._send_call(callId, name, args);
            return result;
        }

        constructor() {
            this.py = getInvoker(this.execute.bind(this));

            this.chan = new Channel();
            this.chan.onOpened = async () => {
                initFunction(this);
            };
            this.chan.onMessage = async msg => {
                if (msg.type === 'return') {
                    // Python returns us value
                    await this._on_return(msg.id, msg.ret)
                } else if (msg.type === 'call') {
                    // Python calls our function
                    await this._on_call(msg.id, msg.name, msg.args);
                } else if (msg.type === 'error') {
                    // Python returned error
                    await this._on_error(msg.id, msg.error);
                } else if (msg.type === 'close') {
                    // TestServer sent shutdown
                    await this._on_close();
                }
            };
            this.chan.onError = async e => {
                console.error(e)
            };
            this.chan.onClose = async () => {
                console.debug('ws conn close');
            };
            window.onbeforeunload = () => this.chan.close();
            this._idCounter = 0;
            this._pendingReturns = [];
            this._fns = {};
        }

        _addReturn(id, resolve, reject) {
            this._pendingReturns.push({id, resolve, reject});
        }

        _popReturn(id) {
            let returnI = this._pendingReturns.findIndex(x => x.id === id);
            if (returnI === -1) {
                throw `no handler for call #${id}`;
            } else {
                let {resolve, reject} = this._pendingReturns[returnI];
                this._pendingReturns.splice(returnI, 1);
                return [resolve, reject];
            }
        }

        async _on_call(id, name, args) {
            console.debug(`received call #${id}: ${name}(${args.join(', ')})`);
            let fn = this._fns[name];

            if (fn === undefined) {
                let fns = Object.keys(this._fns);
                throw `function '${name}' is not found, registered functions: [${fns}]`;
            } else {
                let ret = await fn.apply(this, args);
                await this._send_return(id, name, args, ret);
            }
        }

        async _on_error(id, error) {
            console.debug(`received return error #${id}: ${error}`);
            let [_, reject] = this._popReturn(id);
            reject(error);
        }

        async _on_return(id, ret) {
            console.debug(`received return for #${id} -> ${ret}`);
            let [resolve, _] = this._popReturn(id);
            resolve(ret);
        }

        async _on_close() {
            console.debug('received close message');
            window.close()
        }

        async _send_call(id, name, args) {
            console.debug(`sending call #${id}: ${name}(${args.join(', ')})`);
            await this.chan.send({type: 'call', id, name, args});
        }

        async _send_return(id, name, args, ret) {
            ret = (ret === undefined) ? null : ret;
            console.debug(`sending return for #${id}: ${name}(${args.join(', ')}) -> ${ret}`);
            await this.chan.send({type: 'return', id, ret});
        }
    }

    new Server();
})();

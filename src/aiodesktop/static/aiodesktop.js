(() => {
    let config = window.__aiodesktop__;
    let initFunction = window[config.fn];

    if (initFunction === undefined) {
        console.error(`'[aiodesktop] window' object does not define function: ${initFunction}`)
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

            this._ws_opened_on = null;
            let wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
            this.ws = new WebSocket(`${wsProto}://${window.location.host}${config.ws}`);
            this.ws.onopen = this._on_ws_open.bind(this);
            this.ws.onmessage = this._on_ws_message.bind(this);
            this.ws.onerror = this._on_ws_error.bind(this);
            this.ws.onclose = this._on_abnormal_close.bind(this);
            window.onbeforeunload = () => this.ws.close();
            this._idCounter = 0;
            this._pendingReturns = [];
            this._fns = {};
        }

        async _on_ws_open() {
            this._ws_opened_on = Date.now();
            initFunction && initFunction(this);
        }

        /**
         * @param {MessageEvent} e
         */
        async _on_ws_message(e) {
            let msg = JSON.parse(e.data);

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
                await this._on_normal_close();
            }
        }

        async _on_ws_error(e) {
            console.error(e);
        }

        /**
         * @param {CloseEvent} e
         */
        async _on_abnormal_close(e) {
            // WebSocket has been closed but we didn't receive `close` message,
            // most likely -> server died
            let serverDied = (
                (this._ws_opened_on != null) &&
                (!e.wasClean)
            );
            if (serverDied) {
                window.close();
            }
        }

        async _on_normal_close() {
            console.debug('received close message');
            this.ws.onClose = null;
            window.close()
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

        async _send(data) {
            this.ws.send(JSON.stringify(data));
        }

        async _send_call(id, name, args) {
            console.debug(`sending call #${id}: ${name}(${args.join(', ')})`);
            await this._send({type: 'call', id, name, args});
        }

        async _send_return(id, name, args, ret) {
            ret = (ret === undefined) ? null : ret;
            console.debug(`sending return for #${id}: ${name}(${args.join(', ')}) -> ${ret}`);
            await this._send({type: 'return', id, ret});
        }
    }

    new Server();
})();

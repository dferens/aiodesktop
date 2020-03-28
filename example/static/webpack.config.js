const path = require('path');
const CopyPlugin = require('copy-webpack-plugin');

const dist = path.resolve(__dirname, 'dist');

module.exports = {
    entry: './src/index.js',
    output: {
        filename: 'main.js',
        path: dist,
    },
    module: {
        rules: [
            {
                test: /\.css$/i,
                use: ['style-loader', 'css-loader'],
            },
            {
                test: /\.(png|jpe?g|gif|svg|eot|ttf|woff|woff2)$/i,
                loader: 'url-loader',
            },
        ]
    },
    plugins: [
        new CopyPlugin([
            {
                from: './node_modules/bootstrap/dist/',
                to: path.join(dist, 'bootstrap')
            },
            {
                from: './src/media/',
                to: path.join(dist, 'media')
            }
        ])
    ]
};

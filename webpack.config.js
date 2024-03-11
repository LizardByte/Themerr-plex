const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
  entry: {
    bootstrap: [
      'bootstrap/dist/js/bootstrap.bundle.min.js',
      'bootstrap/dist/css/bootstrap.min.css'
    ],
    fontawesome: '@fortawesome/fontawesome-free/css/all.min.css',
    jquery: 'jquery/dist/jquery.min.js',
    'open-sans': '@fontsource/open-sans/index.css',
  },
  output: {
    filename: 'js/[name].bundle.js',
    path: path.resolve(__dirname, 'Contents', 'Resources', 'web', 'dist'),
  },
  mode: 'production',
  module: {
    rules: [
      {
        test: /\.css$/,
        use: [MiniCssExtractPlugin.loader, 'css-loader'],
      },
    ],
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: 'css/[name].bundle.css',
    }),
  ],
};

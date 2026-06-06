package com.n00bgames.easyduneadmin;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "easy_dune_admin_android";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String DEFAULT_SERVER_URL = "http://127.0.0.1:8089";

    private SharedPreferences prefs;
    private LinearLayout root;
    private WebView webView;
    private ProgressBar progressBar;
    private String serverUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        serverUrl = prefs.getString(KEY_SERVER_URL, "");

        if (serverUrl.isEmpty()) {
            showSetupScreen();
        } else {
            showWebView(serverUrl);
        }
    }

    private void showSetupScreen() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(22), dp(22), dp(22), dp(22));
        root.setBackgroundColor(Color.BLACK);

        TextView title = new TextView(this);
        title.setText("Easy Dune Admin");
        title.setTextColor(Color.rgb(230, 210, 165));
        title.setTextSize(28);
        title.setGravity(Gravity.CENTER);
        root.addView(title, matchWrap());

        TextView help = new TextView(this);
        help.setText("Enter the webadmin URL on your LAN or VPN. Example: " + DEFAULT_SERVER_URL);
        help.setTextColor(Color.rgb(190, 190, 190));
        help.setTextSize(16);
        help.setGravity(Gravity.CENTER);
        help.setPadding(0, dp(16), 0, dp(16));
        root.addView(help, matchWrap());

        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(DEFAULT_SERVER_URL);
        input.setSelectAllOnFocus(true);
        input.setTextColor(Color.WHITE);
        input.setHintTextColor(Color.GRAY);
        input.setHint("http://SERVER-IP:8089");
        input.setBackgroundColor(Color.rgb(18, 18, 18));
        root.addView(input, matchWrap());

        Button connect = duneButton("Connect");
        connect.setOnClickListener(v -> {
            String normalized = normalizeUrl(input.getText().toString());
            if (normalized.isEmpty()) {
                showError("Enter a valid server URL.");
                return;
            }
            prefs.edit().putString(KEY_SERVER_URL, normalized).apply();
            serverUrl = normalized;
            showWebView(normalized);
        });
        root.addView(connect, matchWrap());

        setContentView(root);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void showWebView(String url) {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.BLACK);

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(8), dp(6), dp(8), dp(6));
        toolbar.setBackgroundColor(Color.rgb(12, 8, 4));

        Button back = duneButton("Back");
        back.setOnClickListener(v -> {
            if (webView != null && webView.canGoBack()) {
                webView.goBack();
            }
        });
        toolbar.addView(back, new LinearLayout.LayoutParams(0, dp(42), 1));

        Button reload = duneButton("Reload");
        reload.setOnClickListener(v -> {
            if (webView != null) {
                webView.reload();
            }
        });
        toolbar.addView(reload, new LinearLayout.LayoutParams(0, dp(42), 1));

        Button settings = duneButton("URL");
        settings.setOnClickListener(v -> showUrlDialog());
        toolbar.addView(settings, new LinearLayout.LayoutParams(0, dp(42), 1));

        root.addView(toolbar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setVisibility(View.GONE);
        root.addView(progressBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(3)
        ));

        webView = new WebView(this);
        WebSettings settingsObj = webView.getSettings();
        settingsObj.setJavaScriptEnabled(true);
        settingsObj.setDomStorageEnabled(true);
        settingsObj.setDatabaseEnabled(true);
        settingsObj.setLoadWithOverviewMode(true);
        settingsObj.setUseWideViewPort(true);
        settingsObj.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        settingsObj.setMediaPlaybackRequiresUserGesture(false);

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) {
                    return false;
                }
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
                return true;
            }
        });

        root.addView(webView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1
        ));

        setContentView(root);
        if (!hasNetwork()) {
            showError("No network connection detected. Connect to your LAN/VPN and reload.");
        }
        webView.loadUrl(url);
    }

    private void showUrlDialog() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(serverUrl);
        input.setSelectAllOnFocus(true);

        new AlertDialog.Builder(this)
                .setTitle("Easy Dune Admin URL")
                .setMessage("Use your LAN or VPN URL, for example http://SERVER-IP:8089.")
                .setView(input)
                .setPositiveButton("Save", (dialog, which) -> {
                    String normalized = normalizeUrl(input.getText().toString());
                    if (normalized.isEmpty()) {
                        showError("Enter a valid server URL.");
                        return;
                    }
                    prefs.edit().putString(KEY_SERVER_URL, normalized).apply();
                    serverUrl = normalized;
                    webView.loadUrl(normalized);
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private String normalizeUrl(String rawUrl) {
        String value = rawUrl == null ? "" : rawUrl.trim();
        if (value.isEmpty()) {
            return "";
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://" + value;
        }
        return value;
    }

    private boolean hasNetwork() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) {
            return true;
        }
        NetworkInfo info = manager.getActiveNetworkInfo();
        return info != null && info.isConnected();
    }

    private Button duneButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.rgb(238, 224, 200));
        button.setBackgroundColor(Color.rgb(55, 36, 14));
        button.setAllCaps(false);
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, dp(8), 0, dp(8));
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void showError(String message) {
        new AlertDialog.Builder(this)
                .setTitle("Easy Dune Admin")
                .setMessage(message)
                .setPositiveButton("OK", null)
                .show();
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }
}

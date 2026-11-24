package com.wrapforge.generated

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.DownloadListener
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.app.ActivityCompat
import androidx.appcompat.app.AppCompatActivity
import androidx.browser.customtabs.CustomTabsIntent

class MainActivity : AppCompatActivity() {
    private data class PendingDownload(val uri: Uri, val userAgent: String, val disposition: String?, val mimeType: String?)
    private var pendingDownload: PendingDownload? = null
    private val storagePermissionRequestCode = 7104
    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar
    private lateinit var filePicker: ActivityResultLauncher<String>
    private var pendingFileCallback: android.webkit.ValueCallback<Array<Uri>>? = null
    private val allowedHosts: Set<String> by lazy {
        BuildConfig.ALLOWED_HOSTS.split(',').map { it.trim().lowercase().trimEnd('.') }.filter { it.isNotBlank() }.toSet()
    }

    private fun isTrustedHost(hostname: String?): Boolean {
        val host = hostname?.lowercase()?.trimEnd('.') ?: return false
        return allowedHosts.any { host == it || host.endsWith(".$it") }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!BuildConfig.ALLOW_SCREENSHOTS) window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        window.statusBarColor = getColor(R.color.wrapforge_status_bar)
        window.navigationBarColor = getColor(R.color.wrapforge_navigation_bar)

        filePicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            pendingFileCallback?.onReceiveValue(if (uri != null) arrayOf(uri) else null)
            pendingFileCallback = null
        }
        val root = android.widget.FrameLayout(this)
        webView = WebView(this)
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal)
        progress.max = 100
        progress.visibility = if (BuildConfig.SHOW_LOADING) View.VISIBLE else View.GONE
        root.addView(webView, android.widget.FrameLayout.LayoutParams(-1, -1))
        root.addView(progress, android.widget.FrameLayout.LayoutParams(-1, dp(3)))
        setContentView(root)

        configureWebView()
        webView.loadUrl(BuildConfig.START_URL)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = BuildConfig.JAVASCRIPT_ENABLED
            domStorageEnabled = true
            databaseEnabled = false
            allowFileAccess = false
            allowContentAccess = false
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) safeBrowsingEnabled = true
            setSupportZoom(BuildConfig.ALLOW_ZOOM)
            builtInZoomControls = BuildConfig.ALLOW_ZOOM
            displayZoomControls = false
            loadsImagesAutomatically = true
            cacheMode = WebSettings.LOAD_DEFAULT
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                val scheme = uri.scheme?.lowercase() ?: return true
                if (scheme !in setOf("https", "http")) {
                    return try { startActivity(Intent(Intent.ACTION_VIEW, uri)); true } catch (_: Exception) { true }
                }
                val host = uri.host?.lowercase() ?: return true
                if (scheme == "https" && isTrustedHost(host)) return false
                // External origins never gain the WebView's privileged app context.
                openExternal(uri)
                return true
            }
            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: android.net.http.SslError) {
                handler.cancel()
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView, filePathCallback: android.webkit.ValueCallback<Array<Uri>>, fileChooserParams: FileChooserParams): Boolean {
                if (!BuildConfig.FILE_UPLOADS_ENABLED) return false
                pendingFileCallback?.onReceiveValue(null)
                pendingFileCallback = filePathCallback
                val accept = fileChooserParams.acceptTypes.firstOrNull { it.isNotBlank() } ?: "*/*"
                return try { filePicker.launch(accept); true } catch (_: Exception) { pendingFileCallback = null; false }
            }
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                if (!BuildConfig.SHOW_LOADING) return
                progress.progress = newProgress
                progress.visibility = if (newProgress >= 100) View.GONE else View.VISIBLE
            }
        }
        if (BuildConfig.DOWNLOADS_ENABLED) {
            webView.setDownloadListener(DownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
                val uri = Uri.parse(url)
                if (uri.scheme != "https" || !isTrustedHost(uri.host)) {
                    Toast.makeText(this, "Downloads are limited to the app website", Toast.LENGTH_SHORT).show()
                } else {
                    val pending = PendingDownload(uri, userAgent, contentDisposition, mimeType)
                    if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                        pendingDownload = pending
                        ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), storagePermissionRequestCode)
                    } else {
                        enqueueDownload(pending)
                    }
                }
            })
        }
    }

    private fun enqueueDownload(pending: PendingDownload) {
        val guessed = android.webkit.URLUtil.guessFileName(pending.uri.toString(), pending.disposition, pending.mimeType)
        val safeName = java.io.File(guessed).name.replace(Regex("[^A-Za-z0-9._-]"), "_").trim('.', '_').ifBlank { "download" }
        val request = DownloadManager.Request(pending.uri)
            .setMimeType(pending.mimeType)
            .addRequestHeader("User-Agent", pending.userAgent)
            .setTitle(safeName)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS, safeName)
        (getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
        Toast.makeText(this, "Download started", Toast.LENGTH_SHORT).show()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == storagePermissionRequestCode) {
            val pending = pendingDownload
            pendingDownload = null
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED && pending != null) enqueueDownload(pending)
            else Toast.makeText(this, "Storage permission is required for this download", Toast.LENGTH_SHORT).show()
        }
    }

    private fun openExternal(uri: Uri) {
        try {
            if (BuildConfig.EXTERNAL_LINKS == "in_app_browser") {
                CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(this, uri)
            } else {
                startActivity(Intent(Intent.ACTION_VIEW, uri))
            }
        } catch (_: Exception) {
            Toast.makeText(this, "No browser is available to open this link", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onDestroy() {
        pendingFileCallback?.onReceiveValue(null)
        pendingFileCallback = null
        (webView.parent as? android.view.ViewGroup)?.removeView(webView)
        webView.stopLoading()
        webView.loadUrl("about:blank")
        webView.clearHistory()
        webView.removeAllViews()
        webView.destroy()
        super.onDestroy()
    }
}

import SwiftUI
import WebKit
import SafariServices

struct SafariSheet: Identifiable { let id = UUID(); let url: URL }

struct ContentView: View {
    @State private var progress: Double = 0
    @State private var safariSheet: SafariSheet?
    var body: some View {
        ZStack(alignment: .top) {
            WrapForgeWebView(progress: $progress) { url in safariSheet = SafariSheet(url: url) }
            if BuildConfig.showLoading && progress < 1 {
                ProgressView(value: progress).progressViewStyle(.linear).padding(.top, 1)
            }
        }
        .ignoresSafeArea(edges: [.bottom])
        .sheet(item: $safariSheet) { item in SafariView(url: item.url).ignoresSafeArea() }
    }
}

struct WrapForgeWebView: UIViewRepresentable {
    @Binding var progress: Double
    let openExternal: (URL) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = BuildConfig.javascriptEnabled
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.minimumZoomScale = 1
        webView.scrollView.maximumZoomScale = BuildConfig.allowZoom ? 3 : 1
        context.coordinator.observeProgress(of: webView)
        if let url = URL(string: BuildConfig.startURL) { webView.load(URLRequest(url: url)) }
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKDownloadDelegate {
        private let parent: WrapForgeWebView
        private var progressObservation: NSKeyValueObservation?
        init(_ parent: WrapForgeWebView) { self.parent = parent }
        func observeProgress(of webView: WKWebView) {
            progressObservation = webView.observe(\.estimatedProgress, options: [.new]) { [weak self] webView, _ in
                DispatchQueue.main.async { self?.parent.progress = webView.estimatedProgress }
            }
        }
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url, let scheme = url.scheme?.lowercased() else { decisionHandler(.cancel); return }
            let host = url.host?.lowercased() ?? ""
            let trustedHost = scheme == "https" && BuildConfig.allowedHosts.contains(where: { host == $0 || host.hasSuffix("." + $0) })
            if trustedHost {
                if navigationAction.shouldPerformDownload {
                    decisionHandler(BuildConfig.downloadsEnabled ? .download : .cancel)
                } else {
                    decisionHandler(.allow)
                }
                return
            }
            if scheme == "http" || scheme == "https" {
                if BuildConfig.externalLinks == "in_app_browser" { parent.openExternal(url) }
                else { UIApplication.shared.open(url) }
            } else { UIApplication.shared.open(url) }
            decisionHandler(.cancel)
        }
        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }
        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            download.delegate = self
        }
        func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
            let safeName = URL(fileURLWithPath: suggestedFilename).lastPathComponent
            let destination = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(safeName)
            completionHandler(destination)
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async { self.parent.progress = 1 }
        }
    }
}

struct SafariView: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

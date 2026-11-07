#!/usr/bin/env python3
# Memasang plugin native "Net" (multiplayer lewat IP) ke proyek Android Capacitor.
# Jalankan SETELAH folder android/ ada (setelah `npx cap add android` / `npx cap sync`)
# dan SEBELUM `gradlew assembleDebug`.
import os, re, sys, glob

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
ANDROID = os.path.join(ROOT, "android")
if not os.path.isdir(ANDROID):
    sys.exit("ERROR: folder android/ tidak ditemukan. Taruh langkah ini setelah 'npx cap add android'.")

JAVA_ROOT = os.path.join(ANDROID, "app", "src", "main", "java")
mains = glob.glob(os.path.join(JAVA_ROOT, "**", "MainActivity.java"), recursive=True)
if not mains:
    sys.exit("ERROR: MainActivity.java tidak ditemukan di " + JAVA_ROOT)
main_path = mains[0]
pkg = re.search(r"^\s*package\s+([\w.]+)\s*;", open(main_path, encoding="utf-8").read(), re.M).group(1)
pkg_dir = os.path.dirname(main_path)

NET = r'''package PKG;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONArray;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "Net")
public class NetPlugin extends Plugin {
    private ServerSocket server;
    private Socket sock;
    private OutputStream out;
    private final ExecutorService writer = Executors.newSingleThreadExecutor();

    private synchronized void closeAll() {
        try { if (sock != null) sock.close(); } catch (Exception e) {}
        try { if (server != null) server.close(); } catch (Exception e) {}
        sock = null; server = null; out = null;
    }

    private void status(String s) {
        JSObject o = new JSObject();
        o.put("s", s);
        notifyListeners("status", o);
    }

    private void attach(final Socket s) {
        try {
            s.setTcpNoDelay(true);
            s.setKeepAlive(true);
            synchronized (this) {
                try { if (sock != null) sock.close(); } catch (Exception e) {}
                sock = s;
                out = s.getOutputStream();
            }
        } catch (IOException e) { return; }
        status("connected");
        new Thread(new Runnable() {
            public void run() {
                try {
                    BufferedReader r = new BufferedReader(new InputStreamReader(s.getInputStream(), "UTF-8"));
                    String line;
                    while ((line = r.readLine()) != null) {
                        JSObject o = new JSObject();
                        o.put("data", line);
                        notifyListeners("msg", o);
                    }
                } catch (Exception e) {}
                boolean current;
                synchronized (NetPlugin.this) { current = (sock == s); }
                try { s.close(); } catch (Exception e) {}
                if (current) status("closed");
            }
        }).start();
    }

    @PluginMethod
    public void startServer(final PluginCall call) {
        final int port = call.getInt("port", 8765);
        closeAll();
        try {
            ServerSocket ss = new ServerSocket();
            ss.setReuseAddress(true);
            ss.bind(new InetSocketAddress(port));
            server = ss;
            final ServerSocket fss = ss;
            new Thread(new Runnable() {
                public void run() {
                    try {
                        while (true) {
                            Socket c = fss.accept();
                            attach(c);
                        }
                    } catch (Exception e) {}
                }
            }).start();
            call.resolve();
        } catch (Exception e) {
            call.reject("Gagal membuka port " + port + ": " + e.getMessage());
        }
    }

    @PluginMethod
    public void getIps(PluginCall call) {
        JSONArray arr = new JSONArray();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address && !a.isLoopbackAddress()) arr.put(a.getHostAddress());
                }
            }
        } catch (Exception e) {}
        JSObject o = new JSObject();
        o.put("ips", arr);
        call.resolve(o);
    }

    @PluginMethod
    public void connect(final PluginCall call) {
        final String host = call.getString("host");
        final int port = call.getInt("port", 8765);
        if (host == null || host.length() == 0) { call.reject("IP kosong"); return; }
        closeAll();
        new Thread(new Runnable() {
            public void run() {
                try {
                    Socket s = new Socket();
                    s.connect(new InetSocketAddress(host, port), 4000);
                    attach(s);
                    call.resolve();
                } catch (Exception e) {
                    call.reject("tidak bisa tersambung ke " + host + ":" + port);
                }
            }
        }).start();
    }

    @PluginMethod
    public void send(final PluginCall call) {
        final String d = call.getString("data");
        if (d == null) { call.resolve(); return; }
        writer.execute(new Runnable() {
            public void run() {
                try {
                    OutputStream o;
                    synchronized (NetPlugin.this) { o = out; }
                    if (o != null) { o.write((d + "\n").getBytes("UTF-8")); o.flush(); }
                } catch (Exception e) {}
            }
        });
        call.resolve();
    }

    @PluginMethod
    public void close(PluginCall call) {
        closeAll();
        call.resolve();
    }

    @Override
    protected void handleOnDestroy() { closeAll(); }
}
'''.replace("PKG", pkg)

MAIN = '''package %s;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(NetPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
''' % pkg

open(os.path.join(pkg_dir, "NetPlugin.java"), "w", encoding="utf-8").write(NET)
open(main_path, "w", encoding="utf-8").write(MAIN)

mf = os.path.join(ANDROID, "app", "src", "main", "AndroidManifest.xml")
x = open(mf, encoding="utf-8").read()
need = ["android.permission.INTERNET", "android.permission.ACCESS_WIFI_STATE", "android.permission.ACCESS_NETWORK_STATE"]
add = "".join('    <uses-permission android:name="%s" />\n' % p for p in need if p not in x)
if add:
    x = x.replace("<application", add + "    <application", 1)
    open(mf, "w", encoding="utf-8").write(x)

print("OK: paket =", pkg)
print("OK: NetPlugin.java ditulis di", pkg_dir)
print("OK: MainActivity & izin manifest diperbarui")

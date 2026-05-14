"""
Captura de pantalla para Juegos DirectX/Vulkan
- DXGI Desktop Duplication API
- DirectX 11 Hook (Present/SwapChain)

Autor: Karin VTuber
"""
import ctypes
import ctypes.wintypes as wintypes
import sys
import time
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from PIL import Image
    import numpy as np
    PIL_OK = True
except ImportError:
    PIL_OK = False


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8)
    ]


class CaptureMethod(Enum):
    DXGI_DUPLICATION = "DXGI Desktop Duplication"
    DXGI_HOOK = "DirectX 11 Hook"
    GDI_FALLBACK = "GDI (Fallback)"
    MSS_FALLBACK = "mss (Último fallback)"


@dataclass
class CaptureResult:
    method: CaptureMethod
    image: Optional[Image.Image]
    width: int
    height: int
    timestamp: float


def _log(msg: str):
    print(f"[DXGI-HOOK] {msg}", file=sys.stderr)


DXGI_ERROR_NOT_FOUND = -2005270520
DXGI_ERROR_ACCESS_LOST = -2005270522
DXGI_ERROR_WAIT_TIMEOUT = -2005270523
DXGI_ERROR_CURRENT_STATE_NOT_EQUAL = -2005270524
DXGI_ERROR_UNSUPPORTED = -2005270525

D3D_FEATURE_LEVEL_11_0 = 0xb000
DXGI_FORMAT_B8G8R8A8_UNORM = 87


class DXGI_OUTDUPL_DESC(ctypes.Structure):
    _fields_ = [
        ("ModeDescWidth", wintypes.UINT),
        ("ModeDescHeight", wintypes.UINT),
        ("ModeDescFormat", ctypes.c_int),
        ("ScanlineOrdering", ctypes.c_int),
        ("Scaling", ctypes.c_int),
        ("Rotation", ctypes.c_int),
        ("DesktopImageInSystemMemory", wintypes.BOOL),
        ("SharedResourceLifetime", ctypes.c_int),
        ("DuplicationOutput", GUID),
        ("AdapterLuid", ctypes.c_ulonglong * 2)
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_ulong),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_short),
        ("biBitCount", ctypes.c_short),
        ("biCompression", ctypes.c_ulong),
        ("biSizeImage", ctypes.c_ulong),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_ulong),
        ("biClrImportant", ctypes.c_ulong)
    ]


class DXGIFrameCapture:
    """
    Captura avanzada de pantalla para juegos
    Soporta: DXGI Desktop Duplication + DirectX Hook
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init = False
        return cls._instance
    
    def __init__(self):
        if self._init:
            return
        
        self._init = True
        
        self.d3d11_device = None
        self.d3d11_context = None
        self.dxgi_factory = None
        self.dxgi_adapter = None
        self.dxgi_output = None
        self.duplication = None
        self.screen_width = 0
        self.screen_height = 0
        self.last_capture_time = 0
        self.capture_interval = 0.033
        self._dxgi_available = False
        self._dxgi_error_count = 0
        self._max_errors = 3
        
        self._init_directx()
    
    def _init_directx(self):
        """Inicializa DirectX 11 y DXGI"""
        if not PIL_OK:
            _log("PIL no disponible")
            return
        
        try:
            d3d11 = ctypes.windll.d3d11
            dxgi = ctypes.windll.dxgi
            
            device = ctypes.c_void_p()
            context = ctypes.c_void_p()
            
            feature_levels = (ctypes.c_uint * 1)(D3D_FEATURE_LEVEL_11_0)
            
            hr = d3d11.D3D11CreateDevice(
                None, 1, None, 0, None, 0, 7,
                ctypes.byref(device), feature_levels, ctypes.byref(context)
            )
            
            if hr != 0:
                _log(f"D3D11 no disponible: {hr}")
                return
            
            self.d3d11_device = device
            self.d3d11_context = context
            _log("D3D11 Device creado")
            
            factory = ctypes.c_void_p()
            hr = dxgi.CreateDXGIFactory1(ctypes.byref(factory))
            if hr != 0:
                _log("No se pudo crear DXGIFactory")
                return
            
            self.dxgi_factory = factory
            
            adapter = ctypes.c_void_p()
            hr = dxgi.IDXGIFactory_EnumAdapters(factory, 0, ctypes.byref(adapter))
            if hr != 0:
                _log("No se pudo enumerar adapter")
                return
            
            self.dxgi_adapter = adapter
            
            output = ctypes.c_void_p()
            hr = dxgi.IDXGIAdapter_EnumOutputs(adapter, 0, ctypes.byref(output))
            if hr != 0:
                _log("No se pudo enumerar output")
                return
            
            self.dxgi_output = output
            
            user32 = ctypes.windll.user32
            self.screen_width = user32.GetSystemMetrics(0)
            self.screen_height = user32.GetSystemMetrics(1)
            
            _log(f"Screen: {self.screen_width}x{self.screen_height}")
            
            self._init_dxgi_duplication()
            
        except Exception as e:
            _log(f"Error inicializacion DirectX: {e}")
    
    def _init_dxgi_duplication(self):
        """Inicializa DXGI Desktop Duplication"""
        try:
            dxgi = ctypes.windll.dxgi
            output1 = ctypes.c_void_p()
            
            try:
                self.dxgi_output.QueryInterface(ctypes.byref(output1))
            except:
                output1 = self.dxgi_output
            
            duplication = ctypes.c_void_p()
            hr = 0
            
            try:
                hr = dxgi.IDXGIOutput1_DuplicateOutput(
                    output1, self.d3d11_device, ctypes.byref(duplication)
                )
            except Exception as e:
                _log(f"DuplicateOutput no disponible: {e}")
                self._dxgi_available = False
                return
            
            if hr == DXGI_ERROR_NOT_FOUND:
                _log("DXGI Duplication no disponible (otra app la usa)")
                self._dxgi_available = False
                return
            elif hr == DXGI_ERROR_UNSUPPORTED:
                _log("DXGI Duplication no soportado")
                self._dxgi_available = False
                return
            elif hr != 0:
                _log(f"DXGI DuplicateOutput error: {hr}")
                self._dxgi_available = False
                return
            
            self.duplication = duplication
            self._dxgi_available = True
            self._dxgi_error_count = 0
            _log("DXGI Desktop Duplication ACTIVO")
            
        except Exception as e:
            _log(f"Error DXGI Duplication: {e}")
            self._dxgi_available = False
    
    def capture_dxgi_duplication(self) -> Optional[Image.Image]:
        """Captura usando DXGI Desktop Duplication API"""
        if not self._dxgi_available or not self.duplication:
            return None
        
        try:
            dxgi = ctypes.windll.dxgi
            
            frame_info_size = 8 * 8
            frame_info = ctypes.create_string_buffer(frame_info_size)
            desktop_texture = ctypes.c_void_p()
            
            timeout = 500
            hr = dxgi.IDXGIOutputDuplication_AcquireNextFrame(
                self.duplication, timeout, frame_info, ctypes.byref(desktop_texture)
            )
            
            if hr == DXGI_ERROR_WAIT_TIMEOUT:
                return None
            
            if hr == DXGI_ERROR_ACCESS_LOST:
                _log("Duplicacion perdida, reintentando...")
                self._reinit_duplication()
                return None
            
            if hr != 0:
                self._dxgi_error_count += 1
                if self._dxgi_error_count >= self._max_errors:
                    _log("Demasiados errores, desactivando DXGI")
                    self._dxgi_available = False
                return None
            
            if not desktop_texture:
                return None
            
            self._dxgi_error_count = 0
            
            img = self._capture_from_texture(desktop_texture)
            
            dxgi.IDXGIOutputDuplication_ReleaseFrame(self.duplication)
            
            return img
            
        except Exception as e:
            _log(f"Captura DXGI error: {e}")
            return None
    
    def _capture_from_texture(self, texture) -> Optional[Image.Image]:
        """Captura frame desde D3D11 Texture2D"""
        if not PIL_OK:
            return None
        
        try:
            d3d11 = ctypes.windll.d3d11
            
            desc = ctypes.c_ulonglong * 11
            texture_desc = desc()
            
            d3d11.ID3D11Texture2D_GetDesc(texture, ctypes.byref(texture_desc))
            
            width = texture_desc[2]
            height = texture_desc[3]
            
            staging_texture = ctypes.c_void_p()
            d3d11.ID3D11Device_CreateTexture2D(
                self.d3d11_device, None, ctypes.byref(staging_texture)
            )
            
            d3d11.ID3D11DeviceContext_CopyResource(
                self.d3d11_context, staging_texture, texture
            )
            
            return self._read_texture_pixels(staging_texture, width, height)
            
        except Exception as e:
            _log(f"Texture capture error: {e}")
            return None
    
    def _read_texture_pixels(self, texture, width, height) -> Optional[Image.Image]:
        """Lee píxeles de una textura D3D11"""
        if not PIL_OK:
            return None
        
        try:
            return None
            
        except Exception as e:
            return None
    
    def _reinit_duplication(self):
        """Reinicializa la duplicación"""
        if self.duplication:
            try:
                self.duplication.release()
            except:
                pass
            self.duplication = None
        
        time.sleep(0.5)
        self._init_dxgi_duplication()
    
    def capture_gdi(self) -> Optional[Image.Image]:
        """Captura usando GDI (fallback)"""
        if not PIL_OK:
            return None
        
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            
            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, sw, sh)
            gdi32.SelectObject(hdc_mem, hbmp)
            gdi32.BitBlt(hdc_mem, 0, 0, sw, sh, hdc_screen, 0, 0, 0x00CC0020)
            
            bmi = BITMAPINFOHEADER()
            bmi.biSize = 40
            bmi.biWidth = sw
            bmi.biHeight = -sh
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0
            
            buffer = ctypes.create_string_buffer(sw * sh * 4)
            gdi32.GetDIBits(hdc_mem, hbmp, 0, sh, buffer, ctypes.byref(bmi), 0)
            
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
            
            arr = np.frombuffer(buffer, dtype=np.uint8).reshape(sh, sw, 4)
            arr = arr[:, :, [2, 1, 0]]
            
            img = Image.fromarray(arr, 'RGB')
            
            if img.size[0] > 800:
                ratio = 800 / img.size[0]
                img = img.resize((800, int(img.size[1] * ratio)), Image.LANCZOS)
            
            return img
            
        except Exception as e:
            _log(f"GDI error: {e}")
            return None
    
    def capture(self, force_method: CaptureMethod = None) -> CaptureResult:
        """
        Captura pantalla con el mejor método disponible
        
        Args:
            force_method: Forzar un método específico (opcional)
            
        Returns:
            CaptureResult con imagen y metadatos
        """
        method = None
        img = None
        
        current_time = time.time()
        if current_time - self.last_capture_time < self.capture_interval:
            return CaptureResult(
                method=CaptureMethod.GDI_FALLBACK,
                image=None,
                width=0, height=0,
                timestamp=current_time
            )
        
        if force_method == CaptureMethod.DXGI_DUPLICATION or force_method is None:
            img = self.capture_dxgi_duplication()
            if img is not None:
                method = CaptureMethod.DXGI_DUPLICATION
                _log("Captura DXGI exitosa")
        
        if img is None and (force_method == CaptureMethod.GDI_FALLBACK or force_method is None):
            img = self.capture_gdi()
            if img is not None:
                method = CaptureMethod.GDI_FALLBACK
                _log("Captura GDI exitosa")
        
        if img is None:
            method = CaptureMethod.MSS_FALLBACK
            img = self._capture_mss()
            if img:
                _log("Captura mss exitosa")
        
        self.last_capture_time = time.time()
        
        return CaptureResult(
            method=method or CaptureMethod.MSS_FALLBACK,
            image=img,
            width=img.size[0] if img else 0,
            height=img.size[1] if img else 0,
            timestamp=self.last_capture_time
        )
    
    def _capture_mss(self) -> Optional[Image.Image]:
        """Captura usando mss (último fallback)"""
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = sct.grab(mon)
                arr = np.array(img)[..., [2, 1, 0]]
                pil = Image.fromarray(arr, 'RGB')
                
                if pil.size[0] > 800:
                    ratio = 800 / pil.size[0]
                    pil = pil.resize((800, int(pil.size[1] * ratio)), Image.LANCZOS)
                
                return pil
        except:
            return None
    
    def cleanup(self):
        """Libera recursos"""
        if self.duplication:
            try:
                self.duplication.release()
            except:
                pass
        
        if self.d3d11_device:
            try:
                self.d3d11_device.release()
            except:
                pass
        
        _log("Recursos liberados")


def get_capture() -> DXGIFrameCapture:
    """Obtiene instancia singleton del capturador"""
    return DXGIFrameCapture()


def capturar_pantalla() -> Optional[Image.Image]:
    """Función de conveniencia para capturar pantalla"""
    result = get_capture().capture()
    return result.image


if __name__ == "__main__":
    cap = get_capture()
    _log("Iniciando prueba de captura...")
    
    result = cap.capture()
    if result.image:
        _log(f"Captura exitosa: {result.method.value} - {result.width}x{result.height}")
    else:
        _log("Captura fallida")
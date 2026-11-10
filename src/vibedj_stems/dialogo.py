"""Caixa nativa do Windows para a pessoa escolher onde os stems ficam."""

import ctypes
import os
import uuid
from ctypes import POINTER, byref, c_bool, c_int, c_long, c_ubyte, c_uint, c_ulong, c_ushort, c_void_p, c_wchar_p
from pathlib import Path

# IFileOpenDialog só devolve pasta que existe no sistema de arquivos.
_FOS_PICKFOLDERS = 0x20
_FOS_FORCEFILESYSTEM = 0x40
_FOS_PATHMUSTEXIST = 0x800
_SIGDN_FILESYSPATH = 0x80058000
_COINIT_APARTMENTTHREADED = 0x2
_CLSCTX_INPROC_SERVER = 0x1
_RPC_E_CHANGED_MODE = 0x80010106
_HRESULT_CANCELADO = 0x800704C7
_CLSID_FILE_OPEN_DIALOG = "DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7"
_IID_FILE_OPEN_DIALOG = "D57C7288-D4AD-4768-BE02-9D969532D960"
_TITULO = "Selecione a pasta"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


class _Seletor:
    """Recursos da caixa. `liberar` solta o COM, a janela dona e o apartamento."""

    def __init__(self):
        self.dialogo = c_void_p()
        self.hwnd = None
        self.ole32 = None
        self.user32 = None
        self.soltar_com = False

    def liberar(self) -> None:
        """Solta o que a criação da caixa abriu, na ordem inversa."""
        if self.dialogo:
            _metodo(self.dialogo, 2, c_ulong)(self.dialogo)
            self.dialogo = c_void_p()
        if self.hwnd and self.user32:
            self.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.soltar_com and self.ole32:
            self.ole32.CoUninitialize()
            self.soltar_com = False


def escolher_pasta(titulo: str = _TITULO) -> Path | None:
    """Abre a caixa de pasta e devolve o caminho, ou None se a pessoa cancelar.

    titulo: texto da barra. O fluxo de exportação usa "Selecione a pasta".
    """
    if os.name != "nt":
        return None
    seletor = _criar_seletor(titulo)
    try:
        if not _mostrar(seletor):
            return None
        return Path(_caminho(seletor))
    finally:
        seletor.liberar()


def _guid(texto: str) -> _GUID:
    """Monta um GUID no layout do COM a partir do texto com hífens."""
    valor = uuid.UUID(texto)
    guia = _GUID()
    guia.Data1 = valor.time_low
    guia.Data2 = valor.time_mid
    guia.Data3 = valor.time_hi_version
    for indice, byte in enumerate(valor.bytes[8:]):
        guia.Data4[indice] = byte
    return guia


def _bibliotecas():
    """Cópias próprias de ole32 e user32, para não alterar os argtypes que o ícone da bandeja usa."""
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = [c_void_p, c_ulong]
    ole32.CoInitializeEx.restype = c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [POINTER(_GUID), c_void_p, c_ulong, POINTER(_GUID), POINTER(c_void_p)]
    ole32.CoCreateInstance.restype = c_long
    ole32.CoTaskMemFree.argtypes = [c_void_p]
    ole32.CoTaskMemFree.restype = None
    user32.CreateWindowExW.argtypes = [
        c_ulong, c_wchar_p, c_wchar_p, c_ulong,
        c_int, c_int, c_int, c_int,
        c_void_p, c_void_p, c_void_p, c_void_p,
    ]
    user32.CreateWindowExW.restype = c_void_p
    user32.DestroyWindow.argtypes = [c_void_p]
    user32.DestroyWindow.restype = c_bool
    user32.GetForegroundWindow.restype = c_void_p
    user32.GetWindowThreadProcessId.argtypes = [c_void_p, c_void_p]
    user32.GetWindowThreadProcessId.restype = c_ulong
    user32.AttachThreadInput.argtypes = [c_ulong, c_ulong, c_bool]
    user32.AttachThreadInput.restype = c_bool
    user32.SetForegroundWindow.argtypes = [c_void_p]
    user32.SetForegroundWindow.restype = c_bool
    return ole32, user32


def _metodo(objeto, indice: int, restype, *argtypes):
    """Lê o ponteiro de função na vtable. O primeiro argumento da chamada é o próprio objeto."""
    endereco = ctypes.cast(objeto, c_void_p).value
    vtable = ctypes.cast(endereco, POINTER(c_void_p))[0]
    funcao = ctypes.cast(vtable, POINTER(c_void_p))[indice]
    return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(funcao)


def _exigir(codigo: int, acao: str) -> None:
    """Levanta se o HRESULT não for sucesso. Cancelar a caixa não passa por aqui."""
    if ctypes.c_uint32(codigo).value != 0:
        raise OSError(f"{acao} falhou ({ctypes.c_uint32(codigo).value:#x}).")


def _criar_seletor(titulo: str) -> _Seletor:
    """Cria a caixa, marca que ela só aceita pasta e aplica o título. Ainda não mostra."""
    seletor = _Seletor()
    seletor.ole32, seletor.user32 = _bibliotecas()
    codigo = ctypes.c_uint32(seletor.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)).value
    if codigo == _RPC_E_CHANGED_MODE:
        seletor.soltar_com = False
    elif codigo not in (0, 1):
        raise OSError(f"Não foi possível preparar a caixa de pasta ({codigo:#x}).")
    else:
        seletor.soltar_com = True
    try:
        clsid = _guid(_CLSID_FILE_OPEN_DIALOG)
        iid = _guid(_IID_FILE_OPEN_DIALOG)
        hr = seletor.ole32.CoCreateInstance(
            byref(clsid), None, _CLSCTX_INPROC_SERVER, byref(iid), byref(seletor.dialogo)
        )
        _exigir(hr, "Abrir a caixa de pasta")
        atuais = c_uint()
        # IFileDialog: 9 SetOptions, 10 GetOptions, 17 SetTitle.
        _exigir(_metodo(seletor.dialogo, 10, c_long, POINTER(c_uint))(seletor.dialogo, byref(atuais)), "Ler as opções da caixa")
        flags = atuais.value | _FOS_PICKFOLDERS | _FOS_FORCEFILESYSTEM | _FOS_PATHMUSTEXIST
        _exigir(_metodo(seletor.dialogo, 9, c_long, c_uint)(seletor.dialogo, flags), "Restringir a caixa a pastas")
        _exigir(_metodo(seletor.dialogo, 17, c_long, c_wchar_p)(seletor.dialogo, titulo), "Definir o título da caixa")
        # Dona topmost e sem botão na barra de tarefas, para a caixa aparecer na frente do navegador.
        seletor.hwnd = seletor.user32.CreateWindowExW(
            0x00000008 | 0x00000080, "Static", titulo, 0x80000000,
            0, 0, 0, 0, None, None, None, None,
        )
        return seletor
    except Exception:
        seletor.liberar()
        raise


def _opcoes(seletor: _Seletor) -> int:
    """Máscara atual da caixa. O teste confere o bit de pasta sem chamar Show."""
    atuais = c_uint()
    _exigir(_metodo(seletor.dialogo, 10, c_long, POINTER(c_uint))(seletor.dialogo, byref(atuais)), "Ler as opções da caixa")
    return atuais.value


def _mostrar(seletor: _Seletor) -> bool:
    """Mostra a caixa. False significa que a pessoa cancelou."""
    _trazer_para_frente(seletor)
    # IModalWindow.Show é o índice 3. O HWND dono pode ser nulo.
    codigo = ctypes.c_uint32(_metodo(seletor.dialogo, 3, c_long, c_void_p)(seletor.dialogo, seletor.hwnd)).value
    if codigo == _HRESULT_CANCELADO:
        return False
    _exigir(codigo, "Mostrar a caixa de pasta")
    return True


def _trazer_para_frente(seletor: _Seletor) -> None:
    """Pede o primeiro plano para a thread da caixa, porque o Windows esconde diálogo de thread de fundo."""
    if not seletor.hwnd:
        return
    user32 = seletor.user32
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentThreadId.restype = c_ulong
    frente = user32.GetForegroundWindow()
    atual = kernel32.GetCurrentThreadId()
    outra = user32.GetWindowThreadProcessId(frente, None) if frente else 0
    ligado = bool(outra and outra != atual and user32.AttachThreadInput(atual, outra, True))
    user32.SetForegroundWindow(seletor.hwnd)
    if ligado:
        user32.AttachThreadInput(atual, outra, False)


def _caminho(seletor: _Seletor) -> str:
    """Lê o caminho de sistema da pasta confirmada na caixa."""
    item = c_void_p()
    try:
        # IFileDialog.GetResult é o índice 20. IShellItem.GetDisplayName é o índice 5.
        _exigir(
            _metodo(seletor.dialogo, 20, c_long, POINTER(c_void_p))(seletor.dialogo, byref(item)),
            "Ler a pasta escolhida",
        )
        texto = c_wchar_p()
        _exigir(
            _metodo(item, 5, c_long, c_uint, POINTER(c_wchar_p))(item, _SIGDN_FILESYSPATH, byref(texto)),
            "Ler o caminho da pasta",
        )
        caminho = texto.value
        if texto:
            seletor.ole32.CoTaskMemFree(ctypes.cast(texto, c_void_p))
        if not caminho:
            raise OSError("A caixa de pasta devolveu um caminho vazio.")
        return caminho
    finally:
        if item:
            _metodo(item, 2, c_ulong)(item)

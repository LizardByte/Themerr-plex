import {
    createIcons, ArrowRightCircle, Bird, BookOpenText, Check, ChevronDown,
    ChevronRight, ChevronUp, CircleAlert, CircleCheck, CircleHelp, CircleX,
    Clapperboard, CreditCard, FileCode, FileText, FolderOpen, Globe, HandHeart, Heart,
    House, Info, LogIn, Menu, MessageCircle, MessagesSquare, Monitor,
    Music, Network, RefreshCw, Settings, Smile, TriangleAlert, User, Users, X,
} from 'lucide';

const icons = {
    ArrowRightCircle, Bird, BookOpenText, Check, ChevronDown, ChevronRight,
    ChevronUp, CircleAlert, CircleCheck, CircleHelp, CircleX, Clapperboard,
    CreditCard, FileCode, FileText, FolderOpen, Globe, HandHeart, Heart, House, Info,
    LogIn, Menu, MessageCircle, MessagesSquare, Monitor, Music, Network,
    RefreshCw, Settings, Smile, TriangleAlert, User, Users, X,
};

export function refreshIcons() {
    createIcons({ icons });
}

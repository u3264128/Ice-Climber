// Optional planning accelerator. Final routes are replayed on the Python
// interpreter and native VICE; this executes the same assembled PRG.
#include <cstdint>
using U=uint32_t; using B=uint8_t;
struct State {
    U pc,a,x,y,sp,c,z,i,d,v,n,joy,joy2,raster,bad,wrap_pc;
};
struct CPU {
    State &s; B *m; B *u;   // u: 4KB RAM under $D000-$DFFF, visible by $01
    bool hidden(){B b=m[1];return !((b&3)&&(b&4));}
    B R(U p) {
        p&=65535;
        if(p>=0xd000&&p<0xe000&&hidden())return u[p-0xd000];
        if(p==0xdc00 && m[0xdc02]==0) return B(s.joy);
        if(p==0xdc01) return m[0xdc00]==255 ? B(s.joy2) : 255;
        if(p==0xd012) { if(s.pc==s.wrap_pc)return 0; s.raster=s.raster==250?251:250;return B(s.raster); }
        return m[p];
    }
    void W(U p,U v){p&=65535;if(p>=0xd000&&p<0xe000&&hidden()){u[p-0xd000]=B(v);return;}m[p]=B(v);}
    B F(){B b=R(s.pc);s.pc=(s.pc+1)&65535;return b;}
    U FW(){U lo=F();return lo|(U(F())<<8);}
    U ZW(U p){U lo=R(p&255);return lo|(U(R((p+1)&255))<<8);}
    U A1(U mode){switch(mode){
        case 0:return ZW((F()+s.x)&255);case 1:return F();
        case 2:{U p=s.pc;F();return p;}case 3:return FW();
        case 4:return (ZW(F())+s.y)&65535;case 5:return (F()+s.x)&255;
        case 6:return (FW()+s.y)&65535;default:return (FW()+s.x)&65535;}}
    U A2(U mode,U row){switch(mode){
        case 0:{U p=s.pc;F();return p;}case 1:return F();case 3:return FW();
        case 5:return (F()+((row==4||row==5)?s.y:s.x))&255;
        case 7:return (FW()+(row==5?s.y:s.x))&65535;default:return 0;}}
    void NZ(U a){a&=255;s.z=a==0;s.n=(a>>7)&1;}
    B P(bool brk){return B(s.c|(s.z<<1)|(s.i<<2)|(s.d<<3)|(brk?16:0)|32|(s.v<<6)|(s.n<<7));}
    void PL(B p){s.c=p&1;s.z=(p>>1)&1;s.i=(p>>2)&1;s.d=(p>>3)&1;s.v=(p>>6)&1;s.n=(p>>7)&1;}
    void push(U v){W(256+s.sp,v);s.sp=(s.sp-1)&255;}
    B pop(){s.sp=(s.sp+1)&255;return R(256+s.sp);}
    U popword(){U lo=pop();return lo|(U(pop())<<8);}
    void CMP(U a,U b){s.c=a>=b;NZ(a-b);}
    void ADC(U w){
        U a=s.a,carry=s.c,bin=a+w+carry;s.v=(~(a^w)&(a^bin)&128)!=0;NZ(bin);
        if(s.d){U lo=(a&15)+(w&15)+carry;if(lo>9)lo+=6;
            U hi=(a>>4)+(w>>4)+(lo>15);if(hi>9)hi+=6;s.c=hi>15;s.a=((hi<<4)|(lo&15))&255;}
        else{s.c=bin>255;s.a=bin&255;}
    }
    void SBC(U w){
        int a=s.a,b=1-int(s.c),bin=a-int(w)-b;s.v=((a^int(w))&(a^bin)&128)!=0;s.c=bin>=0;NZ(U(bin));
        if(s.d){int lo=(a&15)-int(w&15)-b,hi=(a>>4)-int(w>>4)-(lo<0);
            if(lo<0)lo-=6;if(hi<0)hi-=6;s.a=U((hi*16)|(lo&15))&255;}
        else s.a=U(bin)&255;
    }
    void branch(bool cond){int8_t off=int8_t(F());if(cond)s.pc=(s.pc+off)&65535;}
    int step(){
        U old=s.pc,op=F(),p=0,val=0,mode=(op>>2)&7,row=op>>5;
        switch(op){
        case 0x00:s.pc=(s.pc+1)&65535;push(s.pc>>8);push(s.pc);push(P(true));s.i=1;s.pc=U(R(0xfffe))|(U(R(0xffff))<<8);return 0;
        case 0x08:push(P(true));return 0;case 0x28:PL(pop());return 0;
        case 0x48:push(s.a);return 0;case 0x68:s.a=pop();NZ(s.a);return 0;
        case 0x20:p=FW();val=(s.pc-1)&65535;push(val>>8);push(val);s.pc=p;return 0;
        case 0x40:PL(pop());s.pc=popword();return 0;case 0x60:s.pc=(popword()+1)&65535;return 0;
        case 0x4c:s.pc=FW();return 0;
        case 0x6c:p=FW();s.pc=U(R(p))|(U(R((p&0xff00)|((p+1)&255)))<<8);return 0;
        case 0x10:branch(!s.n);return 0;case 0x30:branch(s.n);return 0;
        case 0x50:branch(!s.v);return 0;case 0x70:branch(s.v);return 0;
        case 0x90:branch(!s.c);return 0;case 0xb0:branch(s.c);return 0;
        case 0xd0:branch(!s.z);return 0;case 0xf0:branch(s.z);return 0;
        case 0x18:s.c=0;return 0;case 0x38:s.c=1;return 0;
        case 0x58:s.i=0;return 0;case 0x78:s.i=1;return 0;
        case 0xb8:s.v=0;return 0;case 0xd8:s.d=0;return 0;case 0xf8:s.d=1;return 0;
        case 0x24:val=R(F());s.z=(s.a&val)==0;s.n=val>>7;s.v=(val>>6)&1;return 0;
        case 0x2c:val=R(FW());s.z=(s.a&val)==0;s.n=val>>7;s.v=(val>>6)&1;return 0;
        case 0x84:W(F(),s.y);return 0;case 0x94:W((F()+s.x)&255,s.y);return 0;case 0x8c:W(FW(),s.y);return 0;
        case 0xa0:s.y=F();NZ(s.y);return 0;case 0xa4:s.y=R(F());NZ(s.y);return 0;
        case 0xb4:s.y=R((F()+s.x)&255);NZ(s.y);return 0;case 0xac:s.y=R(FW());NZ(s.y);return 0;case 0xbc:s.y=R((FW()+s.x)&65535);NZ(s.y);return 0;
        case 0xc0:CMP(s.y,F());return 0;case 0xc4:CMP(s.y,R(F()));return 0;case 0xcc:CMP(s.y,R(FW()));return 0;
        case 0xe0:CMP(s.x,F());return 0;case 0xe4:CMP(s.x,R(F()));return 0;case 0xec:CMP(s.x,R(FW()));return 0;
        case 0x88:s.y=(s.y-1)&255;NZ(s.y);return 0;case 0xc8:s.y=(s.y+1)&255;NZ(s.y);return 0;
        case 0xca:s.x=(s.x-1)&255;NZ(s.x);return 0;case 0xe8:s.x=(s.x+1)&255;NZ(s.x);return 0;
        case 0x8a:s.a=s.x;NZ(s.a);return 0;case 0xaa:s.x=s.a;NZ(s.x);return 0;
        case 0x98:s.a=s.y;NZ(s.a);return 0;case 0xa8:s.y=s.a;NZ(s.y);return 0;
        case 0x9a:s.sp=s.x;return 0;case 0xba:s.x=s.sp;NZ(s.x);return 0;case 0xea:return 0;
        }
        if((op&3)==1){
            if(row==4&&mode==2){s.bad=old;return op+1;}
            p=A1(mode);if(row!=4)val=R(p);
            switch(row){
            case 0:s.a|=val;NZ(s.a);break;case 1:s.a&=val;NZ(s.a);break;
            case 2:s.a^=val;NZ(s.a);break;case 3:ADC(val);break;
            case 4:W(p,s.a);break;case 5:s.a=val;NZ(s.a);break;
            case 6:CMP(s.a,val);break;case 7:SBC(val);break;
            }return 0;
        }
        if((op&3)==2){
            bool acc=mode==2&&row<4;
            if(!acc && !(mode==1||mode==3||mode==5||mode==7||(mode==0&&row==5))){s.bad=old;return op+1;}
            if(row==4&&(mode==0||mode==7)){s.bad=old;return op+1;}
            if(!acc)p=A2(mode,row);
            if(row==4){W(p,s.x);return 0;}
            val=acc?s.a:R(p);
            U carry=s.c;
            switch(row){
            case 0:s.c=val>>7;val=(val<<1)&255;break;
            case 1:s.c=val>>7;val=((val<<1)|carry)&255;break;
            case 2:s.c=val&1;val>>=1;break;
            case 3:s.c=val&1;val=(val>>1)|(carry<<7);break;
            case 5:s.x=val;NZ(s.x);return 0;
            case 6:val=(val-1)&255;break;case 7:val=(val+1)&255;break;
            }
            if(acc)s.a=val;else W(p,val);NZ(val);return 0;
        }
        s.bad=old;return int(op)+1;
    }
};
extern "C" __declspec(dllexport) int cpu_run(State *s,B *memory,B *under,U target,U limit,const U *skip,U count){
    CPU e{*s,memory,under};
    for(U k=0;k<limit;k++){
        if(s->pc==target)return 0;
        bool skipped=false;
        for(U j=0;j<count;j++)if(s->pc==skip[j]){s->pc=(e.popword()+1)&65535;skipped=true;break;}
        if(!skipped){int error=e.step();if(error)return error;}
    }
    return -1;
}
